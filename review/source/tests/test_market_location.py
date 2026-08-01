from dataclasses import replace

import pandas as pd
import pytest

from itos_platform import DecisionContext, MarketLocationEngine, MarketSnapshot


def candles(closes, *, lows=None, highs=None):
    lows = lows or [value - 1 for value in closes]
    highs = highs or [value + 1 for value in closes]
    return pd.DataFrame({
        "open": closes, "high": highs, "low": lows, "close": closes,
        "volume": [1000] * len(closes),
    })


def context(closes, support=0, resistance=100, **kwargs):
    frame = closes if isinstance(closes, pd.DataFrame) else candles(closes)
    intelligence = kwargs.pop("intelligence", {"support": support, "resistance": resistance, "price": {"atr": 2}})
    return DecisionContext(
        MarketSnapshot({}, intelligence, frame),
        configuration={"market_location": {"minimum_candles": 6}}, **kwargs,
    )


@pytest.mark.parametrize("price,zone", [(10, "BOTTOM"), (25, "LOWER_RANGE"), (50, "MIDDLE"), (75, "UPPER_RANGE"), (90, "TOP")])
def test_static_location_zones(price, zone):
    result = MarketLocationEngine().analyze(context([price] * 6))
    assert result.zone == zone
    assert result.location_score == pytest.approx(price)


@pytest.mark.parametrize("closes,transition,direction", [
    ([45, 46, 47, 48, 49, 50], "MOVING_UP", "BULLISH"),
    ([55, 54, 53, 52, 51, 50], "MOVING_DOWN", "BEARISH"),
])
def test_middle_zone_rotations(closes, transition, direction):
    result = MarketLocationEngine().analyze(context(closes))
    assert result.zone == "MIDDLE"
    assert (result.transition, result.direction) == (transition, direction)


@pytest.mark.parametrize("closes,transition,direction", [
    ([80, 90, 95, 101, 102, 103], "BREAKING_UP", "BULLISH"),
    ([20, 10, 5, -1, -2, -3], "BREAKING_DOWN", "BEARISH"),
])
def test_confirmed_breaks(closes, transition, direction):
    result = MarketLocationEngine().analyze(context(closes))
    assert result.zone == "BREAKOUT_ZONE"
    assert (result.transition, result.direction) == (transition, direction)


@pytest.mark.parametrize("closes,transition,direction", [
    ([90, 101, 103, 102, 101, 100.2], "RETESTING_UP", "BULLISH"),
    ([10, -1, -3, -2, -1, -0.2], "RETESTING_DOWN", "BEARISH"),
    ([90, 101, 103, 102, 99, 98], "FAILED_BREAKOUT", "BEARISH"),
    ([10, -1, -3, -2, 1, 2], "FAILED_BREAKDOWN", "BULLISH"),
])
def test_retests_and_failures(closes, transition, direction):
    result = MarketLocationEngine().analyze(context(closes))
    assert (result.transition, result.direction) == (transition, direction)
    if transition.startswith("RETESTING"):
        assert result.zone == "RETEST_ZONE"
        assert result.retest_level is not None


@pytest.mark.parametrize("raw,flag", [
    (None, "CANDLES_MISSING"),
    (candles([1, 2]), "CANDLES_INSUFFICIENT"),
    (pd.DataFrame({"close": range(6)}), "OHLC_INVALID"),
    (pd.DataFrame({"open": range(6), "high": range(6), "low": range(6), "close": [1, 2, "bad", 4, 5, 6]}), "OHLC_INVALID"),
])
def test_bad_candles_degrade_without_directional_trade(raw, flag):
    snapshot = MarketSnapshot({}, {}, raw)
    result = MarketLocationEngine().analyze(DecisionContext(snapshot))
    assert result.zone == "UNKNOWN"
    assert result.direction == "UNKNOWN"
    assert result.transition == "STABLE"
    assert flag in result.quality_flags


def test_zero_width_range_degrades_safely():
    result = MarketLocationEngine().analyze(context([50] * 6, support=50, resistance=50))
    assert result.zone == "UNKNOWN"
    assert "ZERO_WIDTH_RANGE" in result.quality_flags


def test_swing_fallback_and_validated_levels_are_deterministic():
    frame = candles([20, 30, 40, 50, 60, 70], lows=[10, 20, 25, 30, 40, 50], highs=[25, 35, 45, 55, 80, 75])
    fallback = MarketLocationEngine().analyze(context(frame, intelligence={"price": {"atr": 2}}))
    validated = MarketLocationEngine().analyze(context(frame, support=0, resistance=100))
    assert fallback.support_level == 20
    assert fallback.resistance_level == 80
    assert validated.support_level == 0
    assert validated.resistance_level == 100
    assert {"SUPPORT_UNAVAILABLE", "RESISTANCE_UNAVAILABLE"}.issubset(fallback.quality_flags)


def test_score_is_clamped_and_legacy_mapping_has_parity():
    typed = context([150] * 6)
    result = MarketLocationEngine().analyze(typed)
    legacy = {
        "historical_candles": typed.market_snapshot.historical_candles,
        "intelligence": typed.market_snapshot.intelligence,
        "option_result": {},
        "configuration": typed.configuration,
    }
    assert result.location_score == 100
    assert MarketLocationEngine().analyze(legacy) == result


def test_context_reuses_exact_market_location_instance():
    original = MarketLocationEngine().analyze(context([45, 46, 47, 48, 49, 50]))
    updated = replace(context([50] * 6), market_location=original, engine_results={"market_location": original})
    assert updated.market_location is original
    assert updated.engine_results["market_location"] is original


def test_dashboard_facing_fields_are_typed_and_immutable():
    result = MarketLocationEngine().analyze(context([50] * 6))
    assert result.support_level == 0
    assert result.resistance_level == 100
    with pytest.raises(Exception):
        result.zone = "TOP"


def test_repeated_cached_execution_is_safe_and_recommendation_is_unchanged():
    recommendation = {"side": "CE", "status": "BUY CE", "confirmed": True}
    original = dict(recommendation)
    typed_context = replace(
        context([45, 46, 47, 48, 49, 50]), recommendation=recommendation
    )
    first = MarketLocationEngine().analyze(typed_context)
    second = MarketLocationEngine().analyze(typed_context)
    assert first == second
    assert recommendation == original
