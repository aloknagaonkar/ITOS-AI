"""Deterministic Sprint 12 behavioural contracts (executed locally, not by Codex)."""
from dataclasses import replace

import pandas as pd
import pytest

from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.market_location import MarketLocation
from itos_platform.volume_structure import VolumeStructure, VolumeStructureEngine, VolumeStructureSettings


def location(zone, transition="STABLE"):
    return MarketLocation(zone, 50, transition, 50, "NEUTRAL", .5, 1, 1, 90, 110, None, None, 90, (), ())


def candles(price="RISING", volume="RISING", count=24):
    sign = 1 if price == "RISING" else -1 if price == "FALLING" else 0
    closes = [100 + sign*i*.25 for i in range(count)]
    if volume == "RISING": volumes = [100 + i*12 for i in range(count)]
    elif volume == "FALLING": volumes = [500 - i*12 for i in range(count)]
    else: volumes = [200] * count
    return pd.DataFrame({"open": closes, "high": [x+.2 for x in closes], "low": [x-.2 for x in closes], "close": closes, "volume": volumes})


def analyze(zone, price, volume, transition="STABLE", frame=None):
    snapshot = MarketSnapshot({}, {}, candles(price, volume) if frame is None else frame)
    return VolumeStructureEngine().analyze(DecisionContext(snapshot, market_location=location(zone, transition)))


@pytest.mark.parametrize("zone,price,volume,expected", [
    ("BOTTOM","RISING","RISING","POSSIBLE_ACCUMULATION"),
    ("BOTTOM","RISING","FALLING","WEAK_RALLY"),
    ("BOTTOM","FALLING","RISING","SELLING_CLIMAX_RISK"),
    ("BOTTOM","FALLING","FALLING","WEAK_DECLINE"),
    ("TOP","FALLING","RISING","POSSIBLE_DISTRIBUTION"),
    ("TOP","RISING","FALLING","WEAK_RALLY"),
    ("TOP","RISING","RISING","BUYING_CLIMAX_RISK"),
    ("TOP","FALLING","FALLING","WEAK_DECLINE"),
    ("MIDDLE","RISING","RISING","BULLISH_EXPANSION"),
    ("MIDDLE","FALLING","RISING","BEARISH_EXPANSION"),
    ("MIDDLE","RISING","FALLING","WEAK_RALLY"),
    ("MIDDLE","FALLING","FALLING","WEAK_DECLINE"),
])
def test_location_matrix(zone, price, volume, expected):
    result = analyze(zone, price, volume)
    assert result.interpretation == expected


def test_strong_bullish_breakout_and_weak_breakout():
    assert analyze("BREAKOUT_ZONE","RISING","RISING","BREAKING_UP").interpretation == "BULLISH_EXPANSION"
    assert analyze("BREAKOUT_ZONE","RISING","FALLING","BREAKING_UP").interpretation == "WEAK_RALLY"


def test_constructive_retest_and_failed_breakout():
    assert analyze("RETEST_ZONE","RISING","FALLING","RETESTING_UP").interpretation == "HEALTHY_PULLBACK"
    failed = analyze("TOP","RISING","RISING","FAILED_BREAKOUT")
    assert failed.interpretation == "NEUTRAL"
    assert failed.confidence < 85


def test_flat_price_with_rising_volume_is_absorption():
    result = analyze("MIDDLE","FLAT","RISING")
    assert result.price_direction == "FLAT"
    assert result.effort_result_state == "ABSORPTION"
    assert result.interpretation == "ABSORPTION_DEVELOPING"


def test_absorption_direction_uses_location():
    assert analyze("BOTTOM","FLAT","RISING").direction == "BULLISH"
    assert analyze("TOP","FLAT","RISING").direction == "BEARISH"
    assert analyze("MIDDLE","FLAT","RISING").direction == "NEUTRAL"


@pytest.mark.parametrize("frame,flag", [
    (None, "CANDLES_MISSING"),
    (candles().head(2), "CANDLES_INSUFFICIENT"),
    (candles().drop(columns="volume"), "VOLUME_MISSING"),
    (pd.DataFrame({"open":[1]*8,"high":[2]*8,"low":[0]*8,"close":["bad"]*8,"volume":[1]*8}), "OHLC_INVALID"),
    (candles().assign(volume=0), "VOLUME_INVALID"),
])
def test_invalid_inputs_degrade_safely(frame, flag):
    snapshot = MarketSnapshot({}, {}, frame)
    result = VolumeStructureEngine().analyze(DecisionContext(snapshot, market_location=location("MIDDLE")))
    assert flag in result.quality_flags
    assert result.direction in {"UNKNOWN", "NEUTRAL"}
    assert result.interpretation == "NEUTRAL"


@pytest.mark.parametrize("market_location", [None, location("UNKNOWN")])
def test_location_is_mandatory(market_location):
    result = VolumeStructureEngine().analyze(DecisionContext(MarketSnapshot({}, {}, candles()), market_location=market_location))
    assert result.volume_confirmation == "UNAVAILABLE"
    assert "MARKET_LOCATION_UNAVAILABLE" in result.quality_flags


def test_scores_are_clamped_and_dashboard_fields_exist():
    result = analyze("BOTTOM","RISING","RISING")
    for name in ("price_strength","volume_strength","accumulation_score","distribution_score","absorption_score","exhaustion_score","confidence"):
        assert 0 <= getattr(result, name) <= 100
    assert set(VolumeStructure.__dataclass_fields__) >= {"price_direction","volume_direction","volume_confirmation","effort_result_state","interpretation","explanations"}


def test_context_legacy_mapping_and_identity():
    result = analyze("MIDDLE","RISING","RISING")
    context = DecisionContext(MarketSnapshot({}, {}), engine_results={"volume_structure": result})
    assert context.volume_structure is result
    assert context.engine_results["volume_structure"] is result
    updated = replace(context, volume_structure=result)
    assert updated.volume_structure is result


def test_configuration_controls_minimum_candles():
    engine = VolumeStructureEngine(VolumeStructureSettings(minimum_candles=30))
    result = engine.analyze(DecisionContext(MarketSnapshot({}, {}, candles()), market_location=location("MIDDLE")))
    assert "CANDLES_INSUFFICIENT" in result.quality_flags


def test_malformed_candle_envelope_degrades_safely():
    frame = candles().copy()
    frame.loc[3, "high"] = frame.loc[3, "close"] - 1
    result = analyze("MIDDLE", "RISING", "RISING", frame=frame)
    assert result.interpretation == "NEUTRAL"
    assert "OHLC_INVALID" in result.quality_flags


def test_confirmation_threshold_can_require_stronger_volume_evidence():
    settings = VolumeStructureSettings(confirmation_threshold=1.0)
    context = DecisionContext(
        MarketSnapshot({}, {}, candles("RISING", "RISING")),
        market_location=location("MIDDLE"),
    )
    result = VolumeStructureEngine(settings).analyze(context)
    assert result.volume_confirmation == "NEUTRAL"
    assert "EFFORT_RESULT_UNCONFIRMED" in result.quality_flags


def test_exhaustion_score_uses_configured_spread_window():
    frame = candles("RISING", "FALLING")
    half_spreads = [0.5] * 19 + [0.5, 0.4, 0.3, 0.2, 0.1]
    frame["high"] = frame["close"] + half_spreads
    frame["low"] = frame["close"] - half_spreads
    result = analyze("TOP", "RISING", "FALLING", frame=frame)
    assert result.exhaustion_score >= 15
