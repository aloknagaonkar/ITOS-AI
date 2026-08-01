import subprocess
import sys
from types import SimpleNamespace
from dataclasses import fields

import pandas as pd

from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.decision_pipeline import DecisionPipeline, PipelineResults
from itos_platform.safety_gate_policy import SafetyDecision, SafetyGatePolicy


def test_public_import_boundaries_work_in_fresh_process():
    imports = """
import engines
import itos_platform
import itos_platform.decision_pipeline
import dashboard_application_service
"""
    completed = subprocess.run(
        [sys.executable, "-c", imports],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def _result(**metadata):
    defaults = {"trade_allowed": True, "passed": True, "status": "CONFIRMED", "validated": True}
    defaults.update(metadata)
    return SimpleNamespace(metadata=defaults, vote="CE", score=80)


def test_pipeline_results_legacy_mapping_is_named_and_authoritative():
    result_objects = [_result() for _ in range(22)]
    context = DecisionContext(
        market_snapshot=MarketSnapshot(option_result={}, intelligence={})
    )
    decision = SimpleNamespace(trade_allowed=True, final_state="BUY", blockers=(), reasons=())
    results = PipelineResults(*result_objects, context, decision)

    mapping = results.dashboard_values()
    named_fields = [
        field.name for field in fields(PipelineResults)
        if field.name not in {"decision_context", "safety_decision"}
    ]
    for index, name in enumerate(named_fields):
        assert getattr(results, name) is result_objects[index]
        assert mapping[name] is result_objects[index]
    assert mapping["cycle_result"] is result_objects[0]
    assert mapping["institutional_confidence_result"] is result_objects[15]
    assert mapping["ice_result"] is result_objects[15]
    assert mapping["smart_money_result"] is result_objects[19]
    assert mapping["smi_result"] is result_objects[19]
    assert mapping["data_health_result"] is result_objects[21]


def test_valid_bullish_and_bearish_recommendations_are_not_changed():
    for side in ("CE", "PE"):
        recommendation = {"side": side, "confirmed": True, "status": f"BUY {side}", "blockers": []}
        matching = _result()
        matching.vote = side
        decision = SafetyGatePolicy().enforce(
            recommendation,
            cycle_result=matching,
            stability_result=_result(),
            false_breakout_result=_result(blocked=False),
            confirmation_result=_result(status="CONFIRMED"),
            validation_result=_result(validated=True),
            data_health_result=_result(trading_allowed=True),
        )
        assert decision.trade_allowed is True
        assert recommendation["status"] == f"BUY {side}"


def test_safety_policy_is_monotonic_after_existing_veto():
    recommendation = {"side": "CE", "confirmed": True, "status": "BUY CE", "blockers": []}
    policy = SafetyGatePolicy()
    blocked = policy.enforce(recommendation, false_breakout_result=_result(blocked=True))
    later = policy.enforce(recommendation, validation_result=_result(validated=True))

    assert blocked.trade_allowed is False
    assert later.trade_allowed is False
    assert recommendation["confirmed"] is False
    assert recommendation["status"].startswith("WAIT")


def test_safety_policy_degrades_malformed_and_unhealthy_inputs():
    malformed = {"unexpected": object()}
    malformed_decision = SafetyGatePolicy().enforce(malformed)
    assert malformed_decision.final_state == "WAIT"
    assert malformed["side"] == "WAIT"
    assert malformed["confirmed"] is False

    recommendation = {"side": "PE", "confirmed": True, "status": "BUY PE", "blockers": []}
    unhealthy = SafetyGatePolicy().enforce(
        recommendation,
        data_health_result=_result(trading_allowed=False),
    )
    assert unhealthy.trade_allowed is False
    assert recommendation["status"].startswith("WAIT PE")


def test_decision_context_keeps_market_data_separate_from_results():
    snapshot = MarketSnapshot(
        option_result={"chain": pd.DataFrame()}, intelligence={},
        historical_candles=pd.DataFrame(),
    )
    context = DecisionContext(market_snapshot=snapshot, engine_results={})
    context.engine_results["sentinel"] = _result()
    assert context.market_snapshot is snapshot
    assert not hasattr(snapshot, "engine_results")
