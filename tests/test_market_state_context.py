from types import SimpleNamespace

import pytest

from engines.core_intelligence import MarketEnergyEngine, MarketRegimeEngine, SmartMoneyIndexEngine
from engines.institutional_flow import EarlyWarningEngine
from itos_platform import DecisionContext, MarketSnapshot


def _result(score=80, vote="CE", metadata=None):
    return SimpleNamespace(score=score, vote=vote, metadata={} if metadata is None else metadata)


def _legacy(side="CE"):
    return {
        "option_result": {"summary": {"spot": 112}},
        "intelligence": {"price": {"ema9": 110, "ema21": 100, "vwap": 105, "atr": 5, "rsi": 61}},
        "recommendation": {"side": side, "status": f"BUY {side}", "confirmed": True,
                           "component_scores": {"Momentum": 76, "Volume": 72}},
        "cycle_result": _result(metadata={"phase": "Expansion"}),
        "flow_result": _result(vote=side, metadata={"net_bullish_flow": 45, "oi_acceleration": 2,
                                                     "iv_expansion": 1.5, "gamma_flow": .002,
                                                     "snapshot_count": 5}),
        "ice_result": _result(82, side),
        "validation_result": _result(metadata={"validated": False}),
        "confirmation_result": _result(78, side),
        "stability_result": _result(75, side),
        "false_breakout_result": _result(15, "WAIT"),
    }


def _context(data):
    return DecisionContext(
        MarketSnapshot(data["option_result"], data["intelligence"]),
        recommendation=data["recommendation"], cycle_result=data["cycle_result"],
        flow_result=data["flow_result"], institutional_confidence_result=data["ice_result"],
        validation_result=data["validation_result"], confirmation_result=data["confirmation_result"],
        stability_result=data["stability_result"], false_breakout_result=data["false_breakout_result"],
    )


@pytest.mark.parametrize("side", ["CE", "PE", "WAIT"])
@pytest.mark.parametrize("engine", [MarketRegimeEngine, SmartMoneyIndexEngine, MarketEnergyEngine, EarlyWarningEngine])
def test_legacy_and_decision_context_have_complete_output_parity(engine, side):
    legacy = _legacy(side)
    typed = _context(legacy)
    assert engine().analyze(legacy) == engine().analyze(typed)


@pytest.mark.parametrize("engine", [MarketRegimeEngine, SmartMoneyIndexEngine, MarketEnergyEngine, EarlyWarningEngine])
@pytest.mark.parametrize("malformed", [
    None,
    17,
    {},
    {"intelligence": None},
    {"intelligence": 4},
    {"intelligence": "bad"},
    {"intelligence": {"price": None}},
    {"intelligence": {"price": 17}},
    {"option_result": None},
    {"option_result": []},
    {"option_result": {"summary": None}},
    {"recommendation": None},
    {"recommendation": 17},
    {"recommendation": []},
    {"flow_result": _result(metadata=None)},
    {"flow_result": _result(metadata="bad")},
])
def test_malformed_optional_data_degrades_without_a_trade(engine, malformed):
    result = engine().analyze(malformed)
    assert result.vote == "WAIT"


def test_non_mapping_validation_metadata_does_not_promote_a_trade():
    result = EarlyWarningEngine().analyze({
        "recommendation": None,
        "validation_result": _result(metadata=17),
        "flow_result": _result(metadata=[]),
        "ice_result": _result(99),
    })
    assert result.vote == "WAIT"
    assert result.metadata["state"] == "NO EARLY SETUP"
