"""Sprint 14 behavioural contracts (Codex does not execute this suite)."""
from dataclasses import fields, replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from itos_platform.compression_intelligence import (
    CompressionIntelligenceEngine, CompressionIntelligenceSettings,
)
from itos_platform.decision_context import DecisionContext, MarketSnapshot


def candles(scale=1.0, recent_scale=.25, volume_scale=.5, count=30):
    widths = np.full(count, scale); widths[-8:] = recent_scale
    closes = 100 + np.sin(np.arange(count)/3) * widths
    volume = np.full(count, 1000.0); volume[-5:] *= volume_scale
    return pd.DataFrame({"high": closes+widths, "low": closes-widths, "close": closes, "volume": volume})


def context(frame=None, oi=2.0, proxy=False, transition="RANGE", bias="NEUTRAL", direction="NEUTRAL"):
    frame = candles() if frame is None else frame
    snapshot = MarketSnapshot({"summary": {"futures_oi_change": oi, "futures_oi_proxy": proxy}}, {}, frame)
    return DecisionContext(
        snapshot, recommendation={"side": "WAIT", "status": "WAIT"},
        market_location=SimpleNamespace(transition=transition),
        volume_structure=SimpleNamespace(direction=direction),
        positioning_intelligence=SimpleNamespace(overall_bias=bias),
        institutional_metrics=SimpleNamespace(),
    )


def analyze(frame=None, settings=None, **kwargs):
    return CompressionIntelligenceEngine(settings).analyze(context(frame, **kwargs))


@pytest.mark.parametrize(
    "score,expected",
    [
        (24.99, "NO_COMPRESSION"),
        (25.0, "EARLY_COMPRESSION"),
        (44.99, "EARLY_COMPRESSION"),
        (45.0, "MODERATE_COMPRESSION"),
        (65.0, "HIGH_COMPRESSION"),
        (85.0, "EXTREME_COMPRESSION"),
    ],
)
def test_configured_state_bands_use_exact_boundaries(score, expected):
    settings = CompressionIntelligenceSettings()
    assert settings.early_threshold == 25.0
    assert settings.moderate_threshold == 45.0
    assert settings.high_threshold == 65.0
    assert settings.extreme_threshold == 85.0
    assert CompressionIntelligenceEngine._state(score, settings) == expected


def test_composite_score_rises_as_recent_structure_tightens():
    settings = CompressionIntelligenceSettings(
        volume_weight=0,
        volatility_weight=0,
        time_weight=0,
        oi_weight=0,
    )
    progressively_tighter = (
        analyze(candles(recent_scale=scale, volume_scale=1), settings=settings)
        for scale in (.9, .6, .3)
    )
    scores = [result.compression_score for result in progressively_tighter]
    assert scores[0] < scores[1] < scores[2]


@pytest.mark.parametrize("component", ["atr_compression_score", "range_compression_score", "candle_spread_compression_score", "volume_compression_score", "volatility_compression_score", "time_compression_score"])
def test_each_configured_component_is_reported(component):
    assert getattr(analyze(), component) is not None


def test_oi_build_up_is_optional_and_proxy_is_labelled():
    assert analyze(oi=3).oi_build_score > 0
    missing = analyze(oi=None)
    assert missing.oi_build_score is None and "OI_UNAVAILABLE" in missing.quality_flags
    proxy = analyze(oi=None, proxy=True)
    assert "OI_PROXY_ONLY" in proxy.quality_flags


def test_high_compression_can_have_lower_readiness_without_release():
    result = analyze(candles(recent_scale=.15))
    assert result.compression_score > result.expansion_readiness


@pytest.mark.parametrize("transition,direction", [("BREAKING_UP", "BULLISH"), ("BREAKING_DOWN", "BEARISH")])
def test_release_detected_in_either_direction(transition, direction):
    frame = candles(recent_scale=.2); frame.loc[frame.index[-1], ["high", "low"]] = [102, 98]
    result = analyze(frame, transition=transition, bias=direction, direction=direction)
    assert result.state in {"RELEASING", "EXPANDING"}


def test_expansion_in_progress_requires_range_and_boundary_evidence():
    frame = candles(recent_scale=.2); frame.loc[frame.index[-1], ["high", "low"]] = [103, 97]
    assert analyze(frame, transition="BREAKING_UP").state == "EXPANDING"


def test_direction_is_unconfirmed_when_context_conflicts():
    assert analyze(bias="BULLISH", direction="BEARISH").direction == "UNCONFIRMED"


@pytest.mark.parametrize("bias,direction,transition,expected", [("BULLISH", "BULLISH", "BREAKING_UP", "BULLISH_LEAN"), ("BEARISH", "BEARISH", "BREAKING_DOWN", "BEARISH_LEAN")])
def test_directional_lean_requires_alignment(bias, direction, transition, expected):
    assert analyze(bias=bias, direction=direction, transition=transition).direction == expected


@pytest.mark.parametrize("frame,flag", [(None, "CANDLES_MISSING"), (candles(count=4), "CANDLES_INSUFFICIENT"), (pd.DataFrame({"close": [1]*30}), "OHLC_INVALID")])
def test_missing_or_invalid_candles_degrade(frame, flag):
    ctx = context(candles())
    ctx = replace(ctx, market_snapshot=replace(ctx.market_snapshot, historical_candles=frame))
    result = CompressionIntelligenceEngine().analyze(ctx)
    assert result.state == "UNAVAILABLE" and flag in result.quality_flags


def test_missing_volume_does_not_invalidate_price_compression():
    result = analyze(candles().drop(columns="volume"))
    assert result.state != "UNAVAILABLE" and result.volume_compression_score is None


def test_zero_width_and_malformed_values_degrade_safely():
    flat = pd.DataFrame({"high": [100]*30, "low": [100]*30, "close": [100]*30, "volume": [1]*30})
    assert "ZERO_BASELINE_ATR" in analyze(flat).quality_flags
    malformed = candles()
    malformed["high"] = malformed["high"].astype(object)
    malformed.loc[0, "high"] = "bad"
    ctx = context(malformed)
    recommendation_before = dict(ctx.recommendation)
    result = CompressionIntelligenceEngine().analyze(ctx)
    assert result.state in {"NO_COMPRESSION", "EARLY_COMPRESSION", "MODERATE_COMPRESSION", "HIGH_COMPRESSION", "EXTREME_COMPRESSION"}
    assert ctx.recommendation == recommendation_before
    for score in (result.compression_score, result.energy_stored, result.expansion_readiness, result.confidence):
        assert 0 <= score <= 100


def test_scores_are_clamped_and_model_is_dashboard_complete():
    result = analyze()
    for name in ("compression_score", "energy_stored", "expansion_readiness", "confidence"):
        assert 0 <= getattr(result, name) <= 100
    assert {"display_label", "meaning", "evidence", "contradictions", "explanations"} <= {f.name for f in fields(result)}


def test_missing_dependencies_are_flagged_and_confidence_is_conservative():
    ctx = context()
    ctx = replace(ctx, engine_results={}, market_location=None, volume_structure=None, positioning_intelligence=None, institutional_metrics=None)
    result = CompressionIntelligenceEngine().analyze(ctx)
    assert {"MARKET_LOCATION_UNAVAILABLE", "VOLUME_STRUCTURE_UNAVAILABLE", "POSITIONING_UNAVAILABLE", "INSTITUTIONAL_METRICS_UNAVAILABLE"} <= set(result.quality_flags)


def test_compression_is_informational_only():
    ctx = context(); before = dict(ctx.recommendation)
    CompressionIntelligenceEngine().analyze(ctx)
    assert ctx.recommendation == before == {"side": "WAIT", "status": "WAIT"}


def test_stale_data_applies_critical_input_confidence_ceiling():
    frame = candles(); frame["timestamp"] = pd.date_range("2020-01-01", periods=len(frame), freq="min", tz="UTC")
    result = analyze(frame)
    assert "STALE_DATA" in result.quality_flags
    assert result.confidence <= CompressionIntelligenceSettings().missing_data_confidence_ceiling


def test_component_disagreement_is_explicit():
    frame = candles(recent_scale=1, volume_scale=.1)
    result = analyze(frame)
    assert result.contradictions
    assert "COMPONENTS_CONFLICTED" in result.quality_flags


def test_context_legacy_mapping_reuses_the_identical_result():
    result = analyze()
    ctx = DecisionContext(context().market_snapshot, engine_results={"compression_intelligence": result})
    assert ctx.compression_intelligence is result
    assert ctx.engine_results["compression_intelligence"] is result


def test_unavailable_result_has_safe_dashboard_fields():
    ctx = context(); ctx = replace(ctx, market_snapshot=replace(ctx.market_snapshot, historical_candles=None))
    result = CompressionIntelligenceEngine().analyze(ctx)
    assert result.display_label == "Compression Unavailable"
    assert result.energy_stored == result.expansion_readiness == 0
    assert result.explanations
