"""Behavioural coverage for shadow-only confidence validation and ranking readiness."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from itos_platform.decision_confidence import ConfidencePillar, DecisionConfidence
from itos_platform.decision_confidence_validation import (
    DecisionConfidenceValidationEngine, DecisionConfidenceValidationSettings,
)
from itos_platform.decision_context import DecisionContext, MarketSnapshot


PILLARS = ("MARKET_CONTEXT", "PRICE_VOLUME", "POSITIONING", "COMPRESSION", "MANIPULATION_SAFETY", "INSTITUTIONAL_EVIDENCE", "DATA_QUALITY")


def confidence(score=85, ready=True, pillar_values=None, penalties=(), flags=(), contradictions=0, evidence_quality=85):
    values = pillar_values or [score] * 7
    pillars = tuple(ConfidencePillar(code, code.replace("_", " ").title(), value, 100 / 7, 90, value / 7, "Available", ()) for code, value in zip(PILLARS, values))
    return DecisionConfidence(score, "A", "HIGH_QUALITY", ready, *values, pillars, (), tuple(penalties), (), 100, 0, evidence_quality, contradictions, len(flags), tuple(flags), (), "Point-in-time confidence.")


def point(score, ready=True, pillars=None, penalties=(), blockers=(), contradictions=0, timestamp=None):
    return {"timestamp": timestamp, "score": score, "grade": "A", "setup_quality": "HIGH_QUALITY", "ranking_ready": ready, "pillar_scores": dict(zip(PILLARS, pillars or [score] * 7)), "penalties": penalties, "critical_blockers": blockers, "contradiction_count": contradictions, "evidence_quality": 85}


def context(current=None, history=None, side="WAIT", bias="BULLISH", timestamp="2026-08-02T23:00:00+00:00"):
    evidence = None if bias is None else NS(bias=bias)
    return DecisionContext(MarketSnapshot({}, {}, timestamps={"last_refresh": timestamp}), recommendation={} if side is None else {"side": side, "status": "READY"}, institutional_evidence=evidence, decision_confidence=current, confidence_history=history)


def analyze(scores, **kwargs):
    current_score = scores[-1]
    history = [point(score, ready=kwargs.get("historical_ready", True)) for score in scores[:-1]]
    return DecisionConfidenceValidationEngine(kwargs.get("settings")).analyze(context(confidence(current_score, ready=kwargs.get("ready", True), pillar_values=kwargs.get("pillars"), penalties=kwargs.get("penalties", ()), flags=kwargs.get("flags", ()), contradictions=kwargs.get("contradictions", 0)), history, kwargs.get("side", "WAIT"), kwargs.get("bias", "BULLISH")))


@pytest.mark.parametrize("scores,expected", [([70, 75, 80, 85], "IMPROVING"), ([90, 85, 80, 75], "WEAKENING"), ([84, 85, 84, 85], "STABLE"), ([50, 90, 45, 85], "VOLATILE")])
def test_multi_point_trends_are_deterministic(scores, expected):
    assert analyze(scores).trend == expected


@pytest.mark.parametrize("history", [None, [], [point(80)], [{"score": "bad"}]])
def test_short_missing_and_malformed_history_degrades_safely(history):
    result = DecisionConfidenceValidationEngine().analyze(context(confidence(), history))
    assert result.trend == "INSUFFICIENT_HISTORY"
    assert not result.ranking_eligible
    assert result.confidence <= 55


def test_missing_decision_confidence_is_unavailable_and_never_creates_buy():
    original = {"side": "WAIT", "status": "WAIT"}
    ctx = context(None, [point(80)])
    ctx.recommendation.update(original)
    result = DecisionConfidenceValidationEngine().analyze(ctx)
    assert result.trend == result.ranking_eligibility_state == "UNAVAILABLE"
    assert not result.ranking_eligible and ctx.recommendation == original


def test_history_quality_flags_cover_timestamps_duplicates_staleness_and_missing_pillars():
    old = "2020-01-01T00:00:00+00:00"
    history = [{**point(82), "timestamp": None, "pillar_scores": {}}, point(80, timestamp=old), point(81, timestamp=old)]
    result = DecisionConfidenceValidationEngine().analyze(context(confidence(), history))
    assert {"DUPLICATE_HISTORY_POINTS", "TIMESTAMPS_UNAVAILABLE", "HISTORY_STALE"} <= set(result.quality_flags)


@pytest.mark.parametrize("scores,state", [([80, 80, 80], "VERY_STABLE"), ([80, 85, 90], "STABLE"), ([70, 80, 90], "MODERATE"), ([50, 70, 90], "UNSTABLE"), ([30, 90, 30], "HIGHLY_UNSTABLE")])
def test_stability_bands(scores, state):
    assert analyze(scores).stability_state == state


def test_pillar_agreement_distinguishes_coherence_and_dominance_and_clamps_scores():
    high = analyze([84, 85, 85], pillars=[82, 84, 86, 83, 85, 87, 84])
    low = analyze([84, 85, 85], pillars=[100, 25, 20, 30, 15, 25, 20])
    assert high.pillar_agreement_score > low.pillar_agreement_score
    assert all(0 <= value <= 100 for value in (high.stability_score, high.pillar_agreement_score, high.readiness_persistence, high.confidence))


@pytest.mark.parametrize("ready_values,lower,upper", [([True, True, True], 80, 100), ([False, True, True], 60, 100), ([True, False, True], 0, 80)])
def test_readiness_persistence_reflects_completed_points(ready_values, lower, upper):
    history = [point(83, ready=ready_values[0]), point(84, ready=ready_values[1])]
    result = DecisionConfidenceValidationEngine().analyze(context(confidence(85, ready_values[2]), history))
    assert lower <= result.readiness_persistence <= upper


def test_persistently_ready_coherent_setup_is_eligible():
    result = analyze([83, 84, 85, 86])
    assert result.ranking_eligible and result.ranking_eligibility_state == "ELIGIBLE"


@pytest.mark.parametrize("scores,pillars,flags", [([52, 48, 55, 91], None, ()), ([82, 84, 86, 90], [100, 20, 25, 20, 20, 25, 20], ()), ([82, 84, 86, 90], None, ("STALE_DATA",))])
def test_high_score_does_not_override_instability_disagreement_or_blocker(scores, pillars, flags):
    result = analyze(scores, pillars=pillars, flags=flags)
    assert not result.ranking_eligible


def test_change_drivers_penalties_blockers_and_contradictions_are_compared_canonically():
    before = point(80, pillars=[70] * 7, penalties=("LIQUIDITY_RISK: old wording", "RESOLVED: old"), blockers=("OLD_BLOCKER",), contradictions=2)
    current = confidence(85, pillar_values=[80, 60, 70, 70, 70, 70, 70], penalties=("liquidity risk: new wording", "NEW_PENALTY: now"), contradictions=1)
    result = DecisionConfidenceValidationEngine().analyze(context(current, [before]))
    assert result.strongest_improving_pillar == "MARKET_CONTEXT"
    assert result.weakest_deteriorating_pillar == "PRICE_VOLUME"
    assert len(result.new_penalties) == len(result.resolved_penalties) == 1
    assert result.resolved_blockers == ("OLD_BLOCKER",)
    assert any("Contradiction count decreased" in item for item in result.positive_change_drivers)


@pytest.mark.parametrize("side,bias,alignment", [("BUY CE", "BULLISH", "ALIGNED"), ("BUY PE", "BEARISH", "ALIGNED"), ("BUY CE", "BEARISH", "CONFLICTED"), ("WAIT", "BULLISH", "RECOMMENDATION_WAIT"), (None, "BULLISH", "UNAVAILABLE")])
def test_recommendation_comparison_is_shadow_only(side, bias, alignment):
    result = analyze([83, 84, 85], side=side, bias=bias)
    assert result.recommendation_alignment == alignment


def test_result_is_immutable_and_shared_context_contract_is_explicit():
    result = analyze([83, 84, 85])
    with pytest.raises(FrozenInstanceError):
        result.trend = "CHANGED"
    rebuilt = context(confidence(), [point(80)])
    rebuilt = DecisionContext(**{**vars(rebuilt), "decision_confidence_validation": result})
    assert rebuilt.decision_confidence_validation is result
    assert rebuilt.engine_results["decision_confidence_validation"] is result


def test_configured_ranking_threshold_boundary_is_inclusive():
    settings = DecisionConfidenceValidationSettings(ranking_eligibility_score_threshold=85)
    assert analyze([85, 85, 85], settings=settings).ranking_eligible
