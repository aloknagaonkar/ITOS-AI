"""Behavioural contract for Sprint 16's shadow-only evidence view."""
from types import SimpleNamespace as NS

from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.institutional_evidence import InstitutionalEvidenceEngine


def context(**changes):
    values = dict(
        market_snapshot=MarketSnapshot(option_result={}, intelligence={}),
        market_location=NS(zone="LOWER_RANGE", direction="UP", confidence=85),
        volume_structure=NS(direction="BULLISH", price_direction="RISING", volume_confirmation="CONFIRMED", price_strength=80, accumulation_score=82, distribution_score=0, confidence=85, interpretation="ACCUMULATION"),
        positioning_intelligence=NS(dominant_state="LONG_BUILDUP", overall_confidence=82),
        compression_intelligence=NS(state="RELEASING", direction="BULLISH", energy_stored=75, expansion_readiness=80, confidence=75),
        manipulation_intelligence=NS(state="NO_MANIPULATION", false_breakdown_detected=False, false_breakout_detected=False, bear_trap_risk=5, bull_trap_risk=5, trap_severity=5, confidence=80, follow_through_quality=85, risk_label="Low"),
        institutional_metrics=NS(pcr=NS(weighted_pcr=1.2), liquidity=NS(thin_market=False), volatility=NS(atm_iv=14), greeks=NS(gamma=.1), quality_flags=()),
        flow_result=NS(metadata={"direction":"BULLISH", "score":80, "confidence":80}),
    )
    values.update(changes)
    return DecisionContext(**values)


def test_aligned_bullish_evidence_is_explainable_and_clamped():
    result = InstitutionalEvidenceEngine().analyze(context())
    assert result.bias in {"BULLISH", "STRONGLY_BULLISH"}
    assert result.bullish_score > result.bearish_score
    assert all(0 <= value <= 100 for value in (result.bullish_score, result.bearish_score, result.neutral_score, result.evidence_quality, result.confidence))
    assert {item.source for item in result.bullish_evidence} >= {"VolumeStructure", "PositioningIntelligence", "InstitutionalFlow"}
    assert all((item.code and item.label and item.explanation) for item in result.bullish_evidence)


def test_failed_breakout_preserves_contradiction_and_reduces_confidence():
    clean = InstitutionalEvidenceEngine().analyze(context())
    risky = context(manipulation_intelligence=NS(state="FALSE_BREAKOUT", false_breakdown_detected=False, false_breakout_detected=True, bear_trap_risk=0, bull_trap_risk=90, trap_severity=85, confidence=90, follow_through_quality=20, risk_label="High"))
    result = InstitutionalEvidenceEngine().analyze(risky)
    assert result.bearish_evidence
    assert result.contradictions
    assert result.confidence < clean.confidence


def test_missing_inputs_are_not_neutral_and_degrade_safely():
    result = InstitutionalEvidenceEngine().analyze(DecisionContext(market_snapshot=MarketSnapshot(option_result={}, intelligence={})))
    assert result.bias == "UNAVAILABLE"
    assert result.neutral_evidence == ()
    assert "Market location unavailable" in result.missing_evidence
    assert result.confidence <= 30
    assert "Missing confirmation" in result.narrative


def test_covering_and_unwinding_use_lower_reliability_with_caveats():
    covering = InstitutionalEvidenceEngine().analyze(context(positioning_intelligence=NS(dominant_state="SHORT_COVERING", overall_confidence=80)))
    unwinding = InstitutionalEvidenceEngine().analyze(context(positioning_intelligence=NS(dominant_state="LONG_UNWINDING", overall_confidence=80)))
    cover_item = next(item for item in covering.bullish_evidence if item.code == "POSITIONING_SHORT_COVERING")
    unwind_item = next(item for item in unwinding.bearish_evidence if item.code == "POSITIONING_LONG_UNWINDING")
    assert cover_item.reliability < 80 and "less sustainable" in cover_item.explanation
    assert unwind_item.reliability < 80 and "weaker" in unwind_item.explanation


def test_call_and_put_buying_retain_hedging_caveats():
    call = InstitutionalEvidenceEngine().analyze(context(positioning_intelligence=NS(dominant_state="CALL_BUYING", overall_confidence=80)))
    put = InstitutionalEvidenceEngine().analyze(context(positioning_intelligence=NS(dominant_state="PUT_BUYING", overall_confidence=80)))
    assert "hedging" in next(i for i in call.bullish_evidence if i.code == "POSITIONING_CALL_BUYING").explanation
    assert "protection" in next(i for i in put.bearish_evidence if i.code == "POSITIONING_PUT_BUYING").explanation


def test_evidence_engine_never_changes_recommendation():
    recommendation = {"side":"CE", "status":"BUY CE", "confirmed":True}
    before = dict(recommendation)
    InstitutionalEvidenceEngine().analyze(context(recommendation=recommendation))
    assert recommendation == before
