import pandas as pd
import pytest
from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.institutional_metrics import (
    InstitutionalMetricsEngine,
    InstitutionalMetricsSettings,
)


def chain():
    return pd.DataFrame({
      "strike":[90,100,110],"call_oi":[10,20,30],"put_oi":[30,20,10],
      "call_oi_change":[-2,4,6],"put_oi_change":[6,4,-2],
      "call_volume":[100,200,300],"put_volume":[300,200,100],
      "call_iv":[10,12,14],"put_iv":[14,16,18],
      "call_delta":[.7,.5,.3],"put_delta":[-.3,-.5,-.7],
      "call_gamma":[.01,.02,.03],"put_gamma":[.03,.02,.01],
      "call_theta":[-1,-2,-3],"put_theta":[-3,-2,-1],
      "call_vega":[1,2,3],"put_vega":[3,2,1],
      "call_bid":[9,9,9],"call_ask":[10,10,10],"put_bid":[9,9,9],"put_ask":[10,10,10],
      "call_price_change":[1,-1,-1],"put_price_change":[-1,-1,1]})

def context(frame=None,history=None):
    return DecisionContext(MarketSnapshot({"chain":chain() if frame is None else frame,"summary":{"spot":100}},{}),decision_history=history)

def test_complete_chain_deterministic_metrics_and_signs():
    result=InstitutionalMetricsEngine().analyze(context())
    assert result.oi.call_oi==60 and result.oi.put_oi==60
    assert result.pcr.oi_pcr==pytest.approx(1) and result.pcr.volume_pcr==pytest.approx(1)
    assert result.volatility.iv_skew==pytest.approx(4)
    # OI weighting: call = 26/60 and put = -26/60.
    assert result.greeks.call_delta==pytest.approx(26/60)
    assert result.greeks.put_delta==pytest.approx(-26/60)
    assert result.max_pain==100
    assert result.preview()["dominant_positioning_state"]

def test_empty_and_malformed_chain_are_neutral():
    empty=InstitutionalMetricsEngine().analyze(context(pd.DataFrame()))
    assert empty.positioning.direction=="neutral" and empty.pcr.oi_pcr is None
    malformed=InstitutionalMetricsEngine().analyze(context(pd.DataFrame({"mystery":[1]})))
    assert malformed.positioning.direction=="neutral" and "missing_call_oi" in malformed.quality_flags

def test_zero_denominators_and_missing_optional_data():
    result=InstitutionalMetricsEngine().analyze(context(pd.DataFrame({"strike":[100],"call_oi":[0],"put_oi":[1],"call_oi_change":[0],"put_oi_change":[-2]})))
    assert result.pcr.oi_pcr is None and result.pcr.change_oi_pcr is None
    assert {"incomplete_iv","incomplete_greeks","incomplete_volume","missing_bid_ask"}.issubset(result.quality_flags)
    assert result.positioning.direction=="neutral"

def test_velocity_acceleration_and_percentile_use_timestamped_history():
    history=pd.DataFrame({"timestamp":pd.to_datetime(["2026-01-01 00:00","2026-01-01 00:01","2026-01-01 00:02"]),"call_oi":[10,20,40],"put_oi":[40,30,25],"atm_iv":[10,12,14]})
    result=InstitutionalMetricsEngine().analyze(context(history=history))
    assert result.oi.call_oi_velocity==pytest.approx(20)
    assert result.oi.call_oi_acceleration==pytest.approx(10)
    assert result.oi.put_oi_velocity==pytest.approx(-5)
    assert result.oi.put_oi_acceleration==pytest.approx(5)
    assert result.volatility.iv_percentile==pytest.approx(100)

def test_insufficient_history_is_none_and_flagged():
    result=InstitutionalMetricsEngine().analyze(context(history=pd.DataFrame()))
    assert result.oi.call_oi_velocity is None and result.oi.call_oi_acceleration is None
    assert "insufficient_oi_history" in result.quality_flags

def test_thin_liquidity_and_aliases():
    aliased=pd.DataFrame({"strike_price":[100],"ce_oi":[2],"pe_oi":[4],"ce_volume":[1],"pe_volume":[2]})
    result=InstitutionalMetricsEngine().analyze(context(aliased))
    assert result.pcr.oi_pcr==2 and result.liquidity.thin_market


def test_greek_weighting_method_preserves_signs_and_zero_weights_are_safe():
    weighted_chain = chain()
    weighted_chain["call_volume"] = [30, 20, 10]
    weighted_chain["put_volume"] = [10, 20, 30]

    oi_result = InstitutionalMetricsEngine(
        InstitutionalMetricsSettings(greek_weighting="oi")
    ).analyze(context(weighted_chain))
    volume_result = InstitutionalMetricsEngine(
        InstitutionalMetricsSettings(greek_weighting="volume")
    ).analyze(context(weighted_chain))

    assert oi_result.greeks.call_delta == pytest.approx(26 / 60)
    assert oi_result.greeks.put_delta == pytest.approx(-26 / 60)
    assert volume_result.greeks.call_delta == pytest.approx(34 / 60)
    assert volume_result.greeks.put_delta == pytest.approx(-34 / 60)
    assert oi_result.greeks.call_delta > 0 > oi_result.greeks.put_delta
    assert volume_result.greeks.call_delta > 0 > volume_result.greeks.put_delta

    zero_weight_chain = weighted_chain.copy()
    zero_weight_chain[["call_oi", "put_oi"]] = 0
    zero_weight_result = InstitutionalMetricsEngine(
        InstitutionalMetricsSettings(greek_weighting="oi")
    ).analyze(context(zero_weight_chain))
    assert zero_weight_result.greeks.call_delta is None
    assert zero_weight_result.greeks.put_delta is None
