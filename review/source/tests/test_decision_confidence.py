"""Behavioural coverage for informational Decision Confidence intelligence."""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace as NS

import pytest

from itos_platform.decision_confidence import DecisionConfidenceEngine, DecisionConfidenceSettings
from itos_platform.decision_context import DecisionContext, MarketSnapshot


def context(**changes):
    location = NS(zone="MIDDLE", transition="STABLE", confidence=90, quality_flags=())
    volume = NS(volume_confirmation="CONFIRMED", confidence=90, quality_flags=())
    state = NS(state="LONG_BUILDUP", confidence=90)
    positioning = NS(dominant_state="LONG_BUILDUP", overall_confidence=90, futures=state, options=state, quality_flags=())
    compression = NS(state="BUILDING", confidence=90, quality_flags=())
    manipulation = NS(state="LOW_RISK", manipulation_probability=10, trap_severity=10, confidence=90, quality_flags=())
    evidence = NS(bias="NEUTRAL", confidence=90, evidence_quality=90, contradictions=(), quality_flags=())
    health = NS(score=90, metadata={"flags": [], "trading_allowed": True})
    values = dict(market_location=location, volume_structure=volume, positioning_intelligence=positioning,
                  compression_intelligence=compression, manipulation_intelligence=manipulation,
                  institutional_evidence=evidence, engine_results={"data_health": health})
    values.update(changes)
    return DecisionContext(market_snapshot=MarketSnapshot({}, {}), **values)


def test_strong_setup_is_explainable_and_ranking_ready():
    result = DecisionConfidenceEngine().analyze(context())
    assert result.score >= 70 and result.grade in {"B", "A", "A_PLUS"}
    assert result.ranking_ready
    assert len(result.pillars) == 7
    assert result.contributors and "strongest pillar" in result.narrative.lower()
    assert "weakest" in result.narrative.lower() and "ranking" in result.narrative.lower()
    with pytest.raises(FrozenInstanceError):
        result.score = 1


@pytest.mark.parametrize("score,grade,quality", [
    (95, "A_PLUS", "INSTITUTIONAL_GRADE"), (85, "A", "HIGH_QUALITY"),
    (70, "B", "TRADABLE"), (55, "C", "DEVELOPING"),
    (40, "D", "WEAK"), (0, "AVOID", "AVOID"),
])
def test_configured_grade_and_quality_boundaries(score, grade, quality):
    settings = DecisionConfidenceSettings()
    assert DecisionConfidenceEngine._band(score, settings.grade_thresholds) == grade
    assert DecisionConfidenceEngine._band(score, settings.setup_quality_thresholds) == quality


def test_zero_valid_pillars_returns_unavailable():
    result = DecisionConfidenceEngine().analyze(context(
        market_location=None, volume_structure=None, positioning_intelligence=None,
        compression_intelligence=None, manipulation_intelligence=None,
        institutional_evidence=None, engine_results={}))
    assert (result.score, result.grade, result.setup_quality, result.ranking_ready) == (0, "UNAVAILABLE", "UNAVAILABLE", False)
    assert "DECISION_CONFIDENCE_UNAVAILABLE" in result.quality_flags


@pytest.mark.parametrize("field,ceiling,flag", [
    ("manipulation_intelligence", 70, "MANIPULATION_UNAVAILABLE"),
    ("institutional_evidence", 55, "INSTITUTIONAL_EVIDENCE_UNAVAILABLE"),
    ("positioning_intelligence", 65, "POSITIONING_UNAVAILABLE"),
])
def test_missing_critical_module_applies_visible_ceiling(field, ceiling, flag):
    result = DecisionConfidenceEngine().analyze(context(**{field: None}))
    assert result.confidence_ceiling <= ceiling and flag in result.quality_flags
    assert not result.ranking_ready and result.missing_confirmations


def test_strictest_data_ceiling_wins_and_blocks_ranking():
    health = NS(score=100, metadata={"flags": ["DATA_STALE", "CANDLES_UNAVAILABLE"]})
    result = DecisionConfidenceEngine().analyze(context(engine_results={"data_health": health}))
    assert result.confidence_ceiling == 35
    assert "STALE_DATA" in result.quality_flags and "CRITICAL_CANDLES_MISSING" in result.quality_flags
    assert not result.ranking_ready and result.critical_blocker_count


def test_proxy_and_thin_liquidity_reduce_data_quality_without_duplicate_penalties():
    health = NS(score=90, metadata={"flags": ["PROXY_DATA", "PROXY_DATA", "OPTION_CHAIN_THIN"]})
    result = DecisionConfidenceEngine().analyze(context(engine_results={"data_health": health}))
    assert result.data_quality_score < 90 and result.confidence_ceiling <= 75
    assert sum("PROXY_EVIDENCE:" in item for item in result.penalties) == 1
    assert sum("THIN_LIQUIDITY:" in item for item in result.penalties) == 1


def test_divergence_mixed_positioning_and_compression_conflict_are_explained():
    volume = NS(volume_confirmation="DIVERGENCE", confidence=90, quality_flags=())
    positioning = NS(dominant_state="MIXED", overall_confidence=90, quality_flags=())
    compression = NS(state="CONFLICTED", confidence=90, quality_flags=())
    result = DecisionConfidenceEngine().analyze(context(volume_structure=volume,
        positioning_intelligence=positioning, compression_intelligence=compression))
    assert {item.split(":", 1)[0] for item in result.penalties} >= {
        "VOLUME_DIVERGENCE", "MIXED_POSITIONING", "COMPRESSION_CONFLICT"}
    assert len(result.missing_confirmations) >= 3


def test_manipulation_inverse_risk_and_trap_blocker():
    safe = DecisionConfidenceEngine().analyze(context())
    risky_input = NS(state="TRAP", manipulation_probability=90, trap_severity=85, confidence=95, quality_flags=())
    risky = DecisionConfidenceEngine().analyze(context(manipulation_intelligence=risky_input))
    assert safe.manipulation_safety_score > risky.manipulation_safety_score
    assert not risky.ranking_ready and risky.critical_blocker_count
    assert any("TRAP_SEVERITY" in item for item in risky.penalties)


def test_contradictions_preserved_and_can_block_high_quality_inputs():
    evidence = NS(bias="CONFLICTED", confidence=100, evidence_quality=100,
                  contradictions=("one", "two", "three"), quality_flags=())
    result = DecisionConfidenceEngine().analyze(context(institutional_evidence=evidence))
    assert result.contradiction_count == 3 and not result.ranking_ready
    assert "CONTRADICTIONS_HIGH" in result.quality_flags


def test_weights_normalize_and_contribution_formula_is_deterministic():
    result = DecisionConfidenceEngine(DecisionConfidenceSettings(
        pillar_weights=(("MARKET_CONTEXT", 3), ("PRICE_VOLUME", 3), ("POSITIONING", 3),
                        ("COMPRESSION", 2), ("MANIPULATION_SAFETY", 3),
                        ("INSTITUTIONAL_EVIDENCE", 4), ("DATA_QUALITY", 2)))).analyze(context())
    assert sum(p.weight for p in result.pillars) == pytest.approx(100)
    for pillar in result.pillars:
        assert pillar.contribution == pytest.approx(round(pillar.score * pillar.reliability * pillar.weight / 10000, 4))
        assert all(0 <= value <= 100 for value in (pillar.score, pillar.weight, pillar.reliability, pillar.contribution))


def test_decision_context_and_pipeline_mapping_share_one_instance():
    result = DecisionConfidenceEngine().analyze(context())
    rebuilt = context(decision_confidence=result, engine_results={"decision_confidence": result})
    assert rebuilt.decision_confidence is result
    assert rebuilt.engine_results["decision_confidence"] is result


def test_direction_and_recommendation_confidence_are_not_changed():
    recommendation = {"side": "BUY CE", "status": "READY", "confidence": 63}
    before = dict(recommendation)
    DecisionConfidenceEngine().analyze(context(recommendation=recommendation))
    assert recommendation == before
