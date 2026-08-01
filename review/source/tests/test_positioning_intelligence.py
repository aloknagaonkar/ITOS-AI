"""Behavioural contract for Sprint 13 positioning intelligence."""
from dataclasses import replace

import pandas as pd
import pytest

from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.institutional_metrics import (
    GreeksMetrics, InstitutionalMetrics, LiquidityMetrics, OIMetrics, PCRMetrics,
    PositioningMetrics, VolatilityMetrics,
)
from itos_platform.market_location import MarketLocation
from itos_platform.positioning_intelligence import PositioningIntelligenceEngine
from itos_platform.volume_structure import VolumeStructure


def _volume(price=1.0, confirmation="CONFIRMED", strength=50.0):
    return VolumeStructure("RISING" if price > 0 else "FALLING" if price < 0 else "FLAT", 70, price, .1, "RISING", strength, 20, 1.2, confirmation, "BALANCED", "NEUTRAL", "NEUTRAL", 0, 0, 0, 0, 80, (), ())


def _location(zone="MIDDLE"):
    return MarketLocation(zone, 50, "STABLE", 0, "NEUTRAL", .5, 5, 5, 95, 105, None, None, 80, (), ())


def _metrics(call_oi=0, put_oi=0, call_writing=0, put_writing=0, call_volume=100, put_volume=100, liquidity=80, iv=True, greeks=True):
    return InstitutionalMetrics(
        OIMetrics(call_oi_change=call_oi, put_oi_change=put_oi), PCRMetrics(),
        VolatilityMetrics(call_iv=20 if iv else None, put_iv=21 if iv else None),
        GreeksMetrics(call_delta=.5 if greeks else None, put_delta=-.5 if greeks else None),
        LiquidityMetrics(call_volume, put_volume, call_volume + put_volume, liquidity_score=liquidity, thin_market=liquidity < 25),
        PositioningMetrics(call_writing_score=call_writing, put_writing_score=put_writing),
    )


def _context(price=1, oi=2, metrics=None, chain=None, volume=None, location=None, proxy=False):
    summary = {"option_oi_change" if proxy else "futures_oi_change": oi} if oi is not None else {}
    return DecisionContext(
        MarketSnapshot({"summary": summary, "chain": pd.DataFrame({} if chain is None else chain)}, {}),
        institutional_metrics=metrics, volume_structure=volume or _volume(price),
        market_location=location or _location(),
    )


@pytest.mark.parametrize(("price", "oi", "state"), [
    (1, 2, "LONG_BUILDUP"), (-1, 2, "SHORT_BUILDUP"),
    (1, -2, "SHORT_COVERING"), (-1, -2, "LONG_UNWINDING"),
    (0, 2, "NEUTRAL"), (1, 0, "NEUTRAL"),
])
def test_futures_price_oi_matrix(price, oi, state):
    assert PositioningIntelligenceEngine().analyze(_context(price, oi)).futures.state == state


def test_missing_and_proxy_futures_oi_degrade_safely():
    missing = PositioningIntelligenceEngine().analyze(_context(oi=None)).futures
    proxy = PositioningIntelligenceEngine().analyze(_context(proxy=True)).futures
    assert missing.state == "UNAVAILABLE" and "OI_UNAVAILABLE" in missing.quality_flags
    assert "FUTURES_OI_PROXY_ONLY" in proxy.quality_flags and proxy.confidence <= 55


@pytest.mark.parametrize(("metrics", "chain", "state"), [
    (_metrics(put_oi=20, put_writing=10), {"put_price_change": [-1]}, "PUT_WRITING"),
    (_metrics(call_oi=20, call_writing=10), {"call_price_change": [-1]}, "CALL_WRITING"),
    (_metrics(call_oi=20), {"call_price_change": [1]}, "CALL_BUYING"),
    (_metrics(put_oi=20), {"put_price_change": [1]}, "PUT_BUYING"),
])
def test_options_require_premium_and_demand_confirmation(metrics, chain, state):
    assert PositioningIntelligenceEngine().analyze(_context(metrics=metrics, chain=chain)).options.state == state


def test_oi_alone_does_not_force_options_classification():
    result = PositioningIntelligenceEngine().analyze(_context(metrics=_metrics(put_oi=20, put_writing=10))).options
    assert result.state == "NEUTRAL"
    assert {"CALL_PREMIUM_UNAVAILABLE", "PUT_PREMIUM_UNAVAILABLE"}.issubset(result.quality_flags)


def test_mixed_options_and_thin_liquidity_are_cautious():
    result = PositioningIntelligenceEngine().analyze(_context(
        metrics=_metrics(call_oi=20, put_oi=20, call_writing=10, put_writing=10, liquidity=5),
        chain={"call_price_change": [-1], "put_price_change": [-1]},
    )).options
    assert result.state == "MIXED" and "LIQUIDITY_THIN" in result.quality_flags
    assert 0 <= result.confidence <= 40


def test_missing_optional_inputs_have_explicit_quality_flags():
    result = PositioningIntelligenceEngine().analyze(_context(
        metrics=_metrics(put_oi=20, put_writing=10, iv=False, greeks=False),
        chain={"put_price_change": [-1]},
    )).options
    assert {"IV_UNAVAILABLE", "GREEKS_UNAVAILABLE"}.issubset(result.quality_flags)


def test_volume_confirmation_changes_confidence_without_changing_state():
    confirmed = PositioningIntelligenceEngine().analyze(_context(volume=_volume(1, "CONFIRMED"))).futures
    diverging = PositioningIntelligenceEngine().analyze(_context(volume=_volume(1, "DIVERGING"))).futures
    assert confirmed.state == diverging.state == "LONG_BUILDUP"
    assert confirmed.confidence > diverging.confidence


def test_missing_context_and_malformed_chain_never_create_a_trade():
    context = _context(metrics=None, chain=None)
    context = replace(context, market_location=None, volume_structure=None, recommendation={"side": "WAIT", "status": "WAIT"})
    result = PositioningIntelligenceEngine().analyze(context)
    assert result.futures.state == result.options.state == "UNAVAILABLE"
    assert context.recommendation == {"side": "WAIT", "status": "WAIT"}
    assert 0 <= result.overall_confidence <= 100


def test_location_context_strengthens_conditional_writing():
    metrics = _metrics(put_oi=20, put_writing=10)
    chain = {"put_price_change": [-1]}
    bottom = PositioningIntelligenceEngine().analyze(_context(metrics=metrics, chain=chain, location=_location("BOTTOM"))).options
    middle = PositioningIntelligenceEngine().analyze(_context(metrics=metrics, chain=chain)).options
    assert bottom.state == "PUT_WRITING" and bottom.confidence > middle.confidence


def test_typed_context_requires_volume_structure_for_futures():
    context = replace(_context(), volume_structure=None)
    result = PositioningIntelligenceEngine().analyze(context).futures
    assert result.state == "UNAVAILABLE"
    assert "VOLUME_STRUCTURE_UNAVAILABLE" in result.quality_flags


def test_missing_true_and_proxy_oi_is_unavailable():
    result = PositioningIntelligenceEngine().analyze(_context(oi=None)).futures
    assert result.state == "UNAVAILABLE"
    assert "OI_UNAVAILABLE" in result.quality_flags


def test_opposite_side_missing_premium_does_not_cap_valid_writing():
    put_result = PositioningIntelligenceEngine().analyze(_context(
        metrics=_metrics(put_oi=20, put_writing=10),
        chain={"put_price_change": [-1]}, location=_location("BOTTOM"),
    )).options
    call_result = PositioningIntelligenceEngine().analyze(_context(
        metrics=_metrics(call_oi=20, call_writing=10),
        chain={"call_price_change": [-1]}, location=_location("TOP"),
    )).options
    assert put_result.state == "PUT_WRITING" and put_result.confidence > 40
    assert "CALL_PREMIUM_UNAVAILABLE" in put_result.quality_flags
    assert call_result.state == "CALL_WRITING" and call_result.confidence > 40
    assert "PUT_PREMIUM_UNAVAILABLE" in call_result.quality_flags


@pytest.mark.parametrize(("metrics", "chain", "blocked_state"), [
    (_metrics(call_oi=20, call_writing=10), {"put_price_change": [-1]}, "CALL_WRITING"),
    (_metrics(put_oi=20, put_writing=10), {"call_price_change": [-1]}, "PUT_WRITING"),
])
def test_missing_selected_side_premium_prevents_classification(metrics, chain, blocked_state):
    result = PositioningIntelligenceEngine().analyze(_context(metrics=metrics, chain=chain)).options
    assert result.state == "NEUTRAL"
    assert result.state != blocked_state


def test_top_location_increases_valid_call_writing_confidence():
    metrics = _metrics(call_oi=20, call_writing=10)
    chain = {"call_price_change": [-1]}
    top = PositioningIntelligenceEngine().analyze(_context(metrics=metrics, chain=chain, location=_location("TOP"))).options
    middle = PositioningIntelligenceEngine().analyze(_context(metrics=metrics, chain=chain)).options
    assert top.state == "CALL_WRITING" and top.confidence > middle.confidence


def test_malformed_chain_cannot_create_options_positioning_or_promote_trade():
    recommendation = {"side": "WAIT", "status": "WAIT", "confirmed": False}
    context = replace(
        _context(metrics=_metrics(call_oi=20, put_oi=20), chain={"call_price_change": ["bad"]}),
        recommendation=recommendation,
    )
    result = PositioningIntelligenceEngine().analyze(context)
    assert result.options.state == "NEUTRAL"
    assert context.recommendation == recommendation
    assert context.recommendation["side"] == "WAIT"


def test_typed_missing_volume_ignores_snapshot_price_and_positive_oi():
    context = DecisionContext(
        MarketSnapshot(
            {"summary": {"futures_oi_change": 20}, "chain": pd.DataFrame()},
            {"price": {"change_percent": 2}},
        ),
        recommendation={"side": "WAIT", "status": "WAIT"},
        volume_structure=None,
    )
    result = PositioningIntelligenceEngine().analyze(context)
    assert result.futures.state == "UNAVAILABLE"
    assert "VOLUME_STRUCTURE_UNAVAILABLE" in result.futures.quality_flags
    assert "Canonical volume-structure evidence is unavailable" in result.futures.evidence[0]
    assert context.recommendation == {"side": "WAIT", "status": "WAIT"}


def test_typed_missing_volume_never_calls_legacy_price_fallback():
    class FailingLegacyFallback(PositioningIntelligenceEngine):
        def _legacy_price_change(self, context):
            raise AssertionError("typed input called the legacy fallback")

    result = FailingLegacyFallback().analyze(
        replace(_context(), volume_structure=None)
    )
    assert result.futures.state == "UNAVAILABLE"


def test_legacy_mapping_retains_documented_price_fallback():
    result = PositioningIntelligenceEngine().analyze({
        "option_result": {
            "summary": {"futures_oi_change": 20},
            "chain": pd.DataFrame(),
        },
        "intelligence": {"price": {"change_percent": 2}},
        "recommendation": {"side": "WAIT", "status": "WAIT"},
    })
    assert result.futures.state == "LONG_BUILDUP"
    assert "VOLUME_STRUCTURE_UNAVAILABLE" in result.futures.quality_flags


def test_missing_typed_volume_does_not_suppress_valid_options_state():
    context = replace(
        _context(
            metrics=_metrics(put_oi=20, put_writing=10),
            chain={"put_price_change": [-1]},
            location=_location("BOTTOM"),
        ),
        volume_structure=None,
    )
    result = PositioningIntelligenceEngine().analyze(context)
    assert result.futures.state == "UNAVAILABLE"
    assert result.options.state == "PUT_WRITING"
