"""Behavioural coverage for Sprint 15 manipulation intelligence."""

from dataclasses import fields, replace
from types import SimpleNamespace

import pandas as pd
import pytest

from itos_platform.compression_intelligence import CompressionIntelligence
from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.manipulation_intelligence import (
    ManipulationIntelligence,
    ManipulationIntelligenceEngine,
    ManipulationIntelligenceSettings,
)


def candles(kind="quiet", *, volume=True):
    rows = [
        [99, 100, 98, 99, 100], [99, 101, 98, 100, 105],
        [100, 102, 99, 101, 110], [101, 103, 100, 102, 115],
        [102, 104, 101, 103, 120], [103, 104, 102, 103, 120],
    ]
    if kind == "false_up": rows += [[103, 106, 102.8, 105, 260], [105, 106, 102, 103, 250]]
    elif kind == "false_down": rows += [[103, 103.2, 94, 95, 260], [95, 103, 94, 101, 250]]
    elif kind == "sweep_up": rows += [[103, 106, 102.8, 105, 260], [105, 110, 102, 103, 250]]
    elif kind == "sweep_down": rows += [[103, 103.2, 94, 95, 260], [95, 103, 90, 101, 250]]
    elif kind == "both": rows += [[103, 107, 94, 100, 300], [100, 104, 96, 101, 280]]
    elif kind == "accepted_up": rows += [[103, 106, 103, 105, 200], [105, 108, 104, 107, 220], [107, 110, 106, 109, 230]]
    elif kind == "accepted_down": rows += [[103, 103, 96, 97, 200], [97, 98, 94, 95, 220], [95, 96, 92, 93, 230]]
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    return frame if volume else frame.drop(columns="volume")


def context(kind="quiet", **kwargs):
    frame = kwargs.pop("frame", candles(kind))
    location = kwargs.pop("location", SimpleNamespace(
        zone="TOP" if kind in {"false_up", "sweep_up"} else "BOTTOM" if kind in {"false_down", "sweep_down"} else "MIDDLE",
        support_level=97.0, resistance_level=104.0,
    ))
    volume = kwargs.pop("volume_structure", SimpleNamespace(
        volume_confirmation="DIVERGING" if kind in {"false_up", "false_down", "sweep_up", "sweep_down"} else "CONFIRMED",
        effort_result_state="ABSORPTION" if kind in {"false_up", "false_down", "sweep_up", "sweep_down"} else "BALANCED",
    ))
    return DecisionContext(
        market_snapshot=MarketSnapshot(option_result={}, intelligence={}, historical_candles=frame),
        market_location=location, volume_structure=volume,
        positioning_intelligence=kwargs.pop("positioning", SimpleNamespace(overall_bias="NEUTRAL")),
        compression_intelligence=kwargs.pop("compression", CompressionIntelligence(state="STABLE", quality_flags=())),
        false_breakout_result=kwargs.pop("legacy", SimpleNamespace(metadata={"blocked": False})),
        **kwargs,
    )


@pytest.mark.parametrize("kind, expected, detected_field", [
    ("false_up", "FALSE_BREAKOUT", "false_breakout_detected"),
    ("false_down", "FALSE_BREAKDOWN", "false_breakdown_detected"),
])
def test_failed_acceptance_is_classified(kind, expected, detected_field):
    result = ManipulationIntelligenceEngine().analyze(context(kind))
    assert result.state in {expected, "MANIPULATION_CONFIRMED"}
    assert getattr(result, detected_field) is True
    assert result.return_inside_range


def test_no_manipulation_and_strong_acceptance_are_not_false_moves():
    quiet = ManipulationIntelligenceEngine().analyze(context())
    accepted_up = ManipulationIntelligenceEngine().analyze(context("accepted_up"))
    accepted_down = ManipulationIntelligenceEngine().analyze(context("accepted_down"))
    assert quiet.state == "NO_MANIPULATION"
    assert accepted_up.false_breakout_detected is False
    assert accepted_down.false_breakdown_detected is False
    assert accepted_up.follow_through_quality > quiet.follow_through_quality


@pytest.mark.parametrize("kind, side, direction", [
    ("sweep_up", "ABOVE_RESISTANCE", "BEARISH_TRAP"),
    ("sweep_down", "BELOW_SUPPORT", "BULLISH_TRAP"),
])
def test_liquidity_sweep_stop_hunt_wick_and_direction(kind, side, direction):
    result = ManipulationIntelligenceEngine().analyze(context(kind))
    assert result.liquidity_sweep_detected is True
    assert result.liquidity_sweep_side == side
    assert result.stop_hunt_probability > 0
    assert result.wick_score > 0
    assert result.rejection_score >= ManipulationIntelligenceSettings().rejection_threshold
    assert result.direction == direction
    assert result.range_reentry_speed is not None


def test_false_breakdown_does_not_require_liquidity_sweep_rejection():
    result = ManipulationIntelligenceEngine().analyze(context("false_down"))
    assert result.state in {"FALSE_BREAKDOWN", "MANIPULATION_CONFIRMED"}
    assert result.false_breakdown_detected is True
    assert result.return_inside_range is True
    assert result.liquidity_sweep_detected is False
    assert result.liquidity_sweep_side == "NONE"


def test_wick_without_a_meaningful_level_is_not_enough():
    result = ManipulationIntelligenceEngine().analyze(context(location=SimpleNamespace(zone="MIDDLE", support_level=None, resistance_level=None)))
    assert result.state == "UNAVAILABLE"
    assert "RANGE_UNAVAILABLE" in result.quality_flags


def test_compression_release_adjusts_only_an_existing_event():
    failed = context("false_up", compression=CompressionIntelligence(state="RELEASING", quality_flags=()))
    stable = replace(failed, compression_intelligence=CompressionIntelligence(state="STABLE", quality_flags=()))
    genuine = context("accepted_up", compression=CompressionIntelligence(state="RELEASING", quality_flags=()))
    assert ManipulationIntelligenceEngine().analyze(failed).manipulation_probability >= ManipulationIntelligenceEngine().analyze(stable).manipulation_probability
    assert ManipulationIntelligenceEngine().analyze(genuine).false_breakout_detected is False


@pytest.mark.parametrize("bias, kind, field", [
    ("BULLISH", "false_up", "bull_trap_risk"),
    ("BEARISH", "false_down", "bear_trap_risk"),
])
def test_positioning_is_contextual_and_can_contradict(bias, kind, field):
    contradicted = ManipulationIntelligenceEngine().analyze(context(kind, positioning=SimpleNamespace(overall_bias=bias)))
    neutral = ManipulationIntelligenceEngine().analyze(context(kind))
    assert getattr(contradicted, field) < getattr(neutral, field)
    assert contradicted.contradictions


def test_location_strengthens_relevant_trap_but_middle_does_not_create_one():
    top = ManipulationIntelligenceEngine().analyze(context("false_up"))
    middle = ManipulationIntelligenceEngine().analyze(context("false_up", location=SimpleNamespace(zone="MIDDLE", support_level=97, resistance_level=104)))
    assert top.bull_trap_risk > middle.bull_trap_risk
    assert ManipulationIntelligenceEngine().analyze(context()).false_breakout_detected is False


def test_existing_false_breakout_agreement_and_disagreement_are_explained():
    agrees = ManipulationIntelligenceEngine().analyze(context("false_up", legacy=SimpleNamespace(metadata={"blocked": True})))
    disagrees = ManipulationIntelligenceEngine().analyze(context("false_up"))
    assert any("agrees" in item for item in agrees.evidence)
    assert any("does not agree" in item for item in disagrees.contradictions)


@pytest.mark.parametrize("frame, flag", [
    (None, "CANDLES_MISSING"),
    (pd.DataFrame({"open": [1]}), "OHLC_INVALID"),
    (candles().head(2), "CANDLES_INSUFFICIENT"),
    (pd.DataFrame([[1, 1, 1, 1, 1]]*6, columns=["open", "high", "low", "close", "volume"]), "ZERO_WIDTH_CANDLE"),
])
def test_malformed_or_insufficient_candles_degrade_safely(frame, flag):
    result = ManipulationIntelligenceEngine().analyze(context(frame=frame))
    assert result.state == "UNAVAILABLE"
    assert flag in result.quality_flags
    assert result.confidence <= 5


def test_missing_volume_is_flagged_without_throwing():
    result = ManipulationIntelligenceEngine().analyze(context(frame=candles("false_up", volume=False)))
    assert "VOLUME_UNAVAILABLE" in result.quality_flags
    assert result.state != "UNAVAILABLE"


def test_missing_optional_typed_context_has_confidence_ceiling():
    result = ManipulationIntelligenceEngine().analyze(context("false_up", volume_structure=None, positioning=None, compression=None, legacy=None))
    assert result.confidence <= ManipulationIntelligenceSettings().missing_data_confidence_ceiling
    assert {"VOLUME_STRUCTURE_UNAVAILABLE", "POSITIONING_UNAVAILABLE", "COMPRESSION_UNAVAILABLE", "FALSE_BREAKOUT_EVIDENCE_UNAVAILABLE"}.issubset(result.quality_flags)


def test_conflicting_two_sided_sweep_is_neutral_and_flagged():
    result = ManipulationIntelligenceEngine().analyze(context("both"))
    assert result.direction == "NEUTRAL"
    assert "TRAP_DIRECTION_CONFLICTED" in result.quality_flags


def test_all_numeric_scores_are_clamped_and_model_is_immutable():
    result = ManipulationIntelligenceEngine(ManipulationIntelligenceSettings(contradiction_penalty=-1000)).analyze(context("false_up"))
    numeric = [getattr(result, item.name) for item in fields(ManipulationIntelligence) if item.name in {
        "manipulation_probability", "trap_severity", "breakout_quality", "follow_through_quality", "stop_hunt_probability", "bull_trap_risk", "bear_trap_risk", "rejection_score", "wick_score", "confidence"
    }]
    assert all(0 <= value <= 100 for value in numeric)
    with pytest.raises(Exception):
        result.state = "CHANGED"


def test_legacy_mapping_and_context_share_the_exact_result_instance():
    result = ManipulationIntelligenceEngine().analyze(context("false_up"))
    reconciled = replace(context("false_up"), manipulation_intelligence=result)
    assert reconciled.engine_results["manipulation_intelligence"] is result
    assert reconciled.manipulation_intelligence is result


def test_engine_is_informational_and_never_mutates_recommendation():
    recommendation = {"side": "CE", "status": "BUY CE", "confirmed": True}
    original = recommendation.copy()
    result = ManipulationIntelligenceEngine().analyze(context("false_up", recommendation=recommendation))
    assert result.false_breakout_detected
    assert recommendation == original


def test_dashboard_facing_fields_and_explanations_are_complete():
    result = ManipulationIntelligenceEngine().analyze(context("false_up"))
    assert all(hasattr(result, item.name) for item in fields(ManipulationIntelligence))
    assert result.display_label and result.meaning and result.market_impact
    assert any(item.startswith("What happened:") for item in result.explanations)
    assert any(item.startswith("What it may imply:") for item in result.explanations)
