"""Sprint 13 behavioural contracts (Codex does not execute this suite)."""
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.institutional_metrics import InstitutionalMetricsEngine
from itos_platform.positioning_intelligence import (
    PositioningIntelligenceEngine, PositioningIntelligenceSettings,
)


def chain(call_oi=10, put_oi=10, call_premium=-1, put_premium=-1, volume=100):
    return pd.DataFrame({
        "strike": [100], "call_oi": [100], "put_oi": [100],
        "call_oi_change": [call_oi], "put_oi_change": [put_oi],
        "call_price_change": [call_premium], "put_price_change": [put_premium],
        "call_volume": [volume], "put_volume": [volume],
        "call_iv": [15], "put_iv": [16], "call_delta": [.5], "put_delta": [-.5],
        "call_gamma": [.02], "put_gamma": [.02], "call_theta": [-1], "put_theta": [-1],
        "call_vega": [1], "put_vega": [1], "call_bid": [9], "call_ask": [10],
        "put_bid": [9], "put_ask": [10],
    })


def context(price=1, oi=2, frame=None, zone="MIDDLE", volume_confirmation="CONFIRMED", metrics=True, proxy=False):
    frame = chain() if frame is None else frame
    snapshot = MarketSnapshot(
        {"chain": frame, "summary": {"spot": 100, "futures_oi_change": oi, "futures_oi_proxy": proxy}}, {},
    )
    location = SimpleNamespace(zone=zone)
    volume = SimpleNamespace(price_change_percent=price, volume_confirmation=volume_confirmation, volume_strength=80)
    base = DecisionContext(snapshot, market_location=location, volume_structure=volume)
    institutional = InstitutionalMetricsEngine().analyze(base) if metrics else None
    return replace(base, institutional_metrics=institutional)


def analyze(**kwargs):
    return PositioningIntelligenceEngine().analyze(context(**kwargs))


@pytest.mark.parametrize("price,oi,state", [(1, 2, "LONG_BUILDUP"), (-1, 2, "SHORT_BUILDUP"), (1, -2, "SHORT_COVERING"), (-1, -2, "LONG_UNWINDING")])
def test_futures_matrix(price, oi, state):
    assert analyze(price=price, oi=oi).futures.state == state


@pytest.mark.parametrize("price,oi", [(0.01, 2), (1, .01)])
def test_neutral_bands_do_not_force_positioning(price, oi):
    assert analyze(price=price, oi=oi).futures.state == "NEUTRAL"


def test_missing_oi_is_unavailable():
    result = analyze(oi=None)
    assert result.futures.state == "UNAVAILABLE" and "OI_UNAVAILABLE" in result.quality_flags


def test_proxy_is_explicit_and_confidence_capped():
    result = analyze(oi=None, proxy=True)
    assert "FUTURES_OI_PROXY_ONLY" in result.quality_flags
    assert result.futures.confidence <= PositioningIntelligenceSettings().proxy_data_confidence_ceiling


@pytest.mark.parametrize("frame,state", [
    (chain(call_oi=0, put_oi=30, call_premium=0, put_premium=-1), "PUT_WRITING"),
    (chain(call_oi=30, put_oi=0, call_premium=-1, put_premium=0), "CALL_WRITING"),
    (chain(call_oi=30, put_oi=0, call_premium=1, put_premium=0), "CALL_BUYING"),
    (chain(call_oi=0, put_oi=30, call_premium=0, put_premium=1), "PUT_BUYING"),
])
def test_options_premium_confirmed_behaviours(frame, state):
    assert analyze(frame=frame).options.state == state


@pytest.mark.parametrize("side", ["call", "put"])
def test_oi_without_premium_confirmation_is_not_writing(side):
    frame = chain(call_oi=0, put_oi=0, call_premium=0, put_premium=0)
    frame[f"{side}_oi_change"] = 30
    result = analyze(frame=frame)
    assert result.options.state == "NEUTRAL"
    assert any("lacks decisive premium" in x for x in result.options.contradictions)


def test_mixed_options_evidence_is_not_forced():
    result = analyze(frame=chain(call_oi=30, put_oi=30, call_premium=1, put_premium=1))
    assert result.options.state == "MIXED" and "POSITIONING_CONFLICTED" in result.quality_flags


def test_thin_liquidity_reduces_confidence():
    liquid = analyze(frame=chain(call_oi=0, put_oi=30, call_premium=0, put_premium=-1, volume=20000))
    thin = analyze(frame=chain(call_oi=0, put_oi=30, call_premium=0, put_premium=-1, volume=1))
    assert "LIQUIDITY_THIN" in thin.quality_flags and thin.options.confidence < liquid.options.confidence


@pytest.mark.parametrize("columns,flag", [
    (["call_iv", "put_iv"], "IV_UNAVAILABLE"),
    (["call_gamma", "put_gamma"], "GREEKS_UNAVAILABLE"),
    (["call_price_change", "put_price_change"], "OPTION_PREMIUM_UNAVAILABLE"),
])
def test_missing_options_context_is_flagged(columns, flag):
    assert flag in analyze(frame=chain().drop(columns=columns)).quality_flags


def test_conflicting_price_and_options_is_reported():
    result = analyze(price=-1, oi=2, frame=chain(call_oi=0, put_oi=30, call_premium=0, put_premium=-1))
    assert result.overall_bias == "CONFLICTED"


@pytest.mark.parametrize("zone,state", [("BOTTOM", "PUT_WRITING"), ("TOP", "CALL_WRITING")])
def test_location_confirms_conditional_writing(zone, state):
    frame = chain(call_oi=30 if state == "CALL_WRITING" else 0, put_oi=30 if state == "PUT_WRITING" else 0,
                  call_premium=-1 if state == "CALL_WRITING" else 0, put_premium=-1 if state == "PUT_WRITING" else 0)
    assert any("conditional" in x.lower() for x in analyze(zone=zone, frame=frame).options.evidence)


@pytest.mark.parametrize("zone,price,oi,state", [("TOP", 1, -2, "SHORT_COVERING"), ("BOTTOM", -1, -2, "LONG_UNWINDING")])
def test_climax_location_is_a_futures_contradiction(zone, price, oi, state):
    result = analyze(zone=zone, price=price, oi=oi).futures
    assert result.state == state and result.contradictions


def test_volume_confirmation_increases_and_divergence_decreases_confidence():
    confirmed = analyze(volume_confirmation="CONFIRMED").futures.confidence
    divergent = analyze(volume_confirmation="DIVERGENT").futures.confidence
    assert confirmed > divergent


@pytest.mark.parametrize("frame", [pd.DataFrame(), {"bad": object()}])
def test_malformed_option_chain_safely_degrades(frame):
    result = analyze(frame=frame)
    assert result.options.state in {"UNAVAILABLE", "NEUTRAL"}


def test_missing_institutional_metrics_is_unavailable():
    assert analyze(metrics=False).options.state == "UNAVAILABLE"


@pytest.mark.parametrize("missing,flag", [("volume", "VOLUME_STRUCTURE_UNAVAILABLE"), ("location", "MARKET_LOCATION_UNAVAILABLE")])
def test_missing_context_inputs_are_quality_flagged(missing, flag):
    ctx = context()
    ctx = replace(ctx, **({"volume_structure": None} if missing == "volume" else {"market_location": None}))
    assert flag in PositioningIntelligenceEngine().analyze(ctx).quality_flags


def test_confidence_is_clamped_for_extreme_configuration():
    engine = PositioningIntelligenceEngine(PositioningIntelligenceSettings(price_oi_weight=1000, volume_weight=1000))
    result = engine.analyze(context())
    assert 0 <= result.futures.confidence <= 100 and 0 <= result.overall_confidence <= 100


def test_result_is_informational_and_does_not_mutate_recommendation():
    ctx = replace(context(), recommendation={"side": "WAIT", "status": "WAIT"})
    before = dict(ctx.recommendation)
    result = PositioningIntelligenceEngine().analyze(ctx)
    assert ctx.recommendation == before and not hasattr(result, "recommendation")


def test_dashboard_facing_fields_and_human_meanings_exist():
    result = analyze()
    assert result.futures.meaning and result.futures.market_impact and result.futures.display_state == "Long Buildup"
    assert result.explanations and isinstance(result.quality_flags, tuple)
