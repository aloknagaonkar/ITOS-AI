from dataclasses import replace

import pandas as pd
import pytest

from itos_platform.compression_intelligence import (
    CompressionIntelligenceEngine, CompressionIntelligenceSettings,
)
from itos_platform.decision_context import DecisionContext, MarketSnapshot


def candles(recent_scale=0.25, volume=True, breakout=0.0):
    rows = []
    price = 100.0
    for index in range(30):
        scale = 2.0 if index < 22 else recent_scale
        close = price + (0.08 if index % 2 else -0.08) * scale
        rows.append({"timestamp": f"2026-08-02T{index // 60:02d}:{index % 60:02d}:00Z",
                     "open": price, "high": max(price, close)+scale,
                     "low": min(price, close)-scale, "close": close,
                     **({"volume": 1000-index*20} if volume else {})})
        price = close
    if breakout:
        rows[-2]["close"] += breakout; rows[-2]["high"] += max(breakout, 0)
        rows[-1]["open"] = rows[-2]["close"]
        rows[-1]["close"] = rows[-2]["close"] + breakout
        rows[-1]["high"] = max(rows[-1]["open"], rows[-1]["close"])+2
        rows[-1]["low"] = min(rows[-1]["open"], rows[-1]["close"])-2
    return pd.DataFrame(rows)


def context(raw, **kwargs):
    snapshot = MarketSnapshot({}, {}, raw, {"analysis_cutoff": "2026-08-02T23:59:00Z"})
    return DecisionContext(snapshot, **kwargs)


@pytest.mark.parametrize("raw,flag", [(None, "CANDLES_MISSING"), (pd.DataFrame(), "CANDLES_MISSING"),
                                        ([{"open": 1}], "OHLC_INVALID")])
def test_missing_empty_or_incomplete_candles_are_unavailable(raw, flag):
    result = CompressionIntelligenceEngine().analyze(context(raw))
    assert result.state == "UNAVAILABLE"
    assert flag in result.quality_flags


def test_insufficient_and_malformed_candles_degrade_safely():
    short = candles().head(4)
    assert "CANDLES_INSUFFICIENT" in CompressionIntelligenceEngine().analyze(context(short)).quality_flags
    malformed = candles().copy()
    malformed["close"] = malformed["close"].astype(object)
    malformed.loc[:, "close"] = "bad"
    result = CompressionIntelligenceEngine().analyze(context(malformed))
    assert result.state == "UNAVAILABLE"
    assert "OHLC_INVALID" in result.quality_flags


def test_compression_components_and_scores_are_bounded():
    result = CompressionIntelligenceEngine().analyze(context(candles()))
    assert result.state in {"MODERATE_COMPRESSION", "HIGH_COMPRESSION", "EXTREME_COMPRESSION"}
    scores = (result.compression_score, result.energy_stored, result.expansion_readiness,
              result.atr_compression_score, result.range_compression_score,
              result.candle_spread_compression_score, result.volume_compression_score,
              result.volatility_compression_score, result.time_compression_score)
    assert all(value is None or 0 <= value <= 100 for value in scores)
    assert result.recent_atr < result.baseline_atr


def test_missing_volume_and_oi_keep_price_result_partial():
    result = CompressionIntelligenceEngine().analyze(context(candles(volume=False)))
    assert result.state != "UNAVAILABLE"
    assert result.volume_compression_score is None and result.oi_build_score is None
    assert {"VOLUME_UNAVAILABLE", "OI_UNAVAILABLE"}.issubset(result.quality_flags)
    assert result.confidence <= CompressionIntelligenceSettings().missing_data_confidence_ceiling


def test_zero_width_and_zero_atr_are_not_maximum_compression():
    flat = candles(); flat[["open", "high", "low", "close"]] = 100.0
    result = CompressionIntelligenceEngine().analyze(context(flat))
    assert {"ZERO_BASELINE_ATR", "ZERO_WIDTH_RANGE"}.issubset(result.quality_flags)
    assert result.atr_compression_score is None and result.range_compression_score is None


def test_no_compression_from_expanding_recent_candles():
    result = CompressionIntelligenceEngine().analyze(context(candles(recent_scale=4.0)))
    assert result.state in {"NO_COMPRESSION", "RELEASING", "EXPANDING"}
    assert result.compression_score < CompressionIntelligenceSettings().moderate_threshold


def test_high_compression_does_not_guarantee_release_readiness():
    result = CompressionIntelligenceEngine().analyze(context(candles(recent_scale=0.1)))
    assert result.compression_score > result.expansion_readiness


def test_release_or_expansion_is_detected_from_completed_follow_through():
    result = CompressionIntelligenceEngine().analyze(context(candles(recent_scale=0.15, breakout=5)))
    assert result.state in {"RELEASING", "EXPANDING"}


def test_legacy_mapping_parity_and_input_immutability():
    original = candles(); before = original.copy(deep=True)
    typed = CompressionIntelligenceEngine().analyze(context(original))
    legacy = CompressionIntelligenceEngine().analyze({"historical_candles": original,
        "timestamps": {"analysis_cutoff": "2026-08-02T23:59:00Z"}})
    pd.testing.assert_frame_equal(original, before)
    assert typed.compression_score == legacy.compression_score


def test_decision_context_reconciles_same_compression_instance():
    calculated = CompressionIntelligenceEngine().analyze(context(candles()))
    rebuilt = context(candles(), engine_results={"compression_intelligence": calculated})
    assert rebuilt.compression_intelligence is calculated


def test_analysis_never_mutates_recommendation():
    recommendation = {"side": "BUY CE", "status": "READY", "confidence": 77}
    before = dict(recommendation)
    CompressionIntelligenceEngine().analyze(context([{"broken": object()}], recommendation=recommendation))
    assert recommendation == before
