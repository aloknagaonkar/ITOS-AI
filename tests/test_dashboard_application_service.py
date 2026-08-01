from types import SimpleNamespace

import pandas as pd
import pytest

import dashboard_application_service as service_module
import itos_platform.decision_pipeline as pipeline_module
from dashboard_application_service import (
    DashboardApplicationService,
    DashboardDataUnavailable,
)
from itos_platform.decision_context import DecisionContext, MarketSnapshot


ENGINE_NAMES = [
    "MarketCycleEngine",
    "RecommendationStabilityEngine",
    "PhaseTransitionEngine",
    "PatternRecognitionEngine",
    "TradeReadinessEngine",
    "InstitutionalRadarEngine",
    "MarketStoryEngine",
    "CandleDNAEngine",
    "SmartCandlestickEngine",
    "InstitutionalStructureEngine",
    "InstitutionalFootprintEngine",
    "FalseBreakoutEngine",
    "InstitutionalConfirmationEngine",
    "InstitutionalDecisionMatrixEngine",
    "InstitutionalFlowEngine",
    "InstitutionalConfidenceEngine",
    "SignalValidationEngine",
    "EarlyWarningEngine",
    "MarketRegimeEngine",
    "SmartMoneyIndexEngine",
    "MarketEnergyEngine",
    "DataHealthEngine",
]

EXPECTED_ENGINE_ORDER = ENGINE_NAMES + ["AITradeEngine"]


def _result(name, **metadata):
    defaults = {
        "name": name,
        "trade_allowed": True,
        "passed": True,
        "status": "CONFIRMED",
        "validated": True,
    }
    defaults.update(metadata)
    return SimpleNamespace(
        metadata=defaults,
        vote="CE",
        score=80,
        confidence=80,
        explanation=[name],
    )


@pytest.fixture
def harness(monkeypatch):
    events = []
    calls = {}
    results = {name: _result(name) for name in ENGINE_NAMES}
    chain = pd.DataFrame({"strike": [100], "timestamp": ["unused"]})
    candles = pd.DataFrame({"timestamp": ["2026-07-31T09:15:00"]})
    option_result = {"summary": {"spot": 100}, "chain": chain}
    intelligence = {"price": {"trend": "Neutral"}}
    confidence_history = pd.DataFrame({"side": ["CE"]})
    phase_history = pd.DataFrame({"phase": ["Expansion"]})

    class Client:
        def __init__(self, token):
            events.append(("client", token))

        def get_option_chain(self, instrument, expiry):
            events.append("acquire_option_chain")
            return ["raw"]

        def option_chain_to_dataframe(self, raw):
            events.append("normalize_option_chain")
            return chain

        def get_intraday_candles(self, *args, **kwargs):
            events.append("acquire_intraday_candles")
            return candles

        def get_historical_candles(self, *args, **kwargs):
            events.append("acquire_historical_candles")
            return candles

    class Store:
        def save_snapshot(self, *args):
            events.append("save_snapshot")
            return 41, True

        def get_history(self, *args, **kwargs):
            events.append("read_decision_history")
            return pd.DataFrame()

        def get_strike_history(self, *args, **kwargs):
            events.append("read_strike_history")
            return pd.DataFrame()

        def get_confidence_history(self, *args, **kwargs):
            events.append("read_confidence_history")
            return confidence_history

        def get_phase_history(self, *args, **kwargs):
            events.append("read_phase_history")
            return phase_history

        def get_stability_history(self, *args, **kwargs):
            events.append("read_stability_history")
            return pd.DataFrame()

        def get_trade_history(self, *args, **kwargs):
            events.append("read_trade_history")
            return pd.DataFrame()

        def trade_statistics(self, *args, **kwargs):
            events.append("read_trade_statistics")
            return {"total": 0}

        def save_phase_history(self, *args):
            events.append("save_phase_history")

        def save_stability_history(self, *args):
            events.append("save_stability_history")

        def save_confidence_history(self, *args):
            events.append("save_confidence_history")

        def sync_trade_history(self, *args):
            events.append("sync_trade_history")
            return {"created": 0}

    monkeypatch.setattr(
        service_module,
        "analyse_market",
        lambda df, strikes: events.append("analyse_options") or option_result,
    )
    monkeypatch.setattr(
        service_module,
        "evaluate_price_action",
        lambda df: events.append("analyse_price") or intelligence["price"],
    )
    monkeypatch.setattr(
        service_module,
        "combine_intelligence",
        lambda options, price: events.append("combine_intelligence") or intelligence,
    )
    monkeypatch.setattr(service_module, "institutional_summary", lambda *args: None)

    def recommendation(*args):
        events.append("build_recommendation")
        return {
            "side": "CE",
            "confirmed": True,
            "status": "BUY CE",
            "blockers": [],
            "ce_top5": pd.DataFrame(),
            "pe_top5": pd.DataFrame(),
        }

    monkeypatch.setattr(service_module, "build_recommendation", recommendation)

    def engine_class(name):
        class Engine:
            def __init__(self, *args, **kwargs):
                calls[f"{name}.init"] = (args, kwargs)

            def analyze(self, inputs):
                events.append(name)
                calls[name] = inputs
                return results[name]

        return Engine

    for name in ENGINE_NAMES:
        monkeypatch.setattr(pipeline_module, name, engine_class(name))

    ai_packages = []

    class TradeEngine:
        def build(self, **kwargs):
            events.append("AITradeEngine")
            calls["AITradeEngine"] = kwargs
            package = {
                "decision": "BUY" if kwargs["recommendation"]["confirmed"] else "WAIT",
                "source": "AITradeEngine",
            }
            ai_packages.append(package)
            return package

    monkeypatch.setattr(service_module, "AITradeEngine", TradeEngine)
    return SimpleNamespace(
        events=events,
        calls=calls,
        results=results,
        Client=Client,
        Store=Store,
        option_result=option_result,
        intelligence=intelligence,
        ai_packages=ai_packages,
        confidence_history=confidence_history,
        phase_history=phase_history,
    )


def _execute(harness, *, should_load=True, state=None, client_factory=None):
    return DashboardApplicationService(
        client_factory=client_factory or harness.Client,
        store_factory=harness.Store,
        clock=lambda: "10:11:12",
    ).execute(
        token="token",
        instrument_key="NSE|TEST",
        underlying="TEST",
        expiry="2026-08-06",
        timeframe=5,
        strikes=8,
        save_snapshots=True,
        history_hours=8,
        should_load=should_load,
        session_state={} if state is None else state,
    )


def test_service_preserves_pipeline_outputs_session_keys_and_order(harness):
    state = {}
    result = _execute(harness, state=state)

    assert harness.events[:9] == [
        ("client", "token"),
        "acquire_option_chain",
        "normalize_option_chain",
        "analyse_options",
        "acquire_intraday_candles",
        "acquire_historical_candles",
        "analyse_price",
        "combine_intelligence",
        "save_snapshot",
    ]
    engine_events = [event for event in harness.events if event in EXPECTED_ENGINE_ORDER]
    assert engine_events == EXPECTED_ENGINE_ORDER
    assert harness.events.index("build_recommendation") < harness.events.index("MarketCycleEngine")
    for write in (
        "save_phase_history",
        "save_stability_history",
        "save_confidence_history",
        "sync_trade_history",
    ):
        assert harness.events.index("build_recommendation") < harness.events.index(write)
    phase_reads = [
        index
        for index, event in enumerate(harness.events)
        if event == "read_phase_history"
    ]
    confidence_reads = [
        index
        for index, event in enumerate(harness.events)
        if event == "read_confidence_history"
    ]
    assert len(phase_reads) == 2
    assert len(confidence_reads) == 2
    assert phase_reads[0] < harness.events.index("RecommendationStabilityEngine")
    assert confidence_reads[0] < harness.events.index("RecommendationStabilityEngine")
    assert harness.events.index("save_phase_history") < phase_reads[-1]
    assert harness.events.index("save_confidence_history") < confidence_reads[-1]
    assert harness.events.index("save_confidence_history") < harness.events.index("sync_trade_history")

    assert state["option_result"] is harness.option_result
    assert state["intelligence"] is harness.intelligence
    assert result.cycle_result is harness.results["MarketCycleEngine"]
    assert result.stability_result is harness.results["RecommendationStabilityEngine"]
    assert result.flow_result is harness.results["InstitutionalFlowEngine"]
    assert result.ice_result is harness.results["InstitutionalConfidenceEngine"]
    assert result.validation_result is harness.results["SignalValidationEngine"]
    assert result.early_warning_result is harness.results["EarlyWarningEngine"]
    assert result.regime_result is harness.results["MarketRegimeEngine"]
    assert result.decision_matrix_result is harness.results["InstitutionalDecisionMatrixEngine"]
    assert result.trade_plan_result is None
    assert result.ai_trade_opportunity is harness.ai_packages[-1]
    assert result.ai_trade_opportunity == {"decision": "BUY", "source": "AITradeEngine"}
    assert result.cycle_meta is result.cycle_result.metadata
    assert result.stability_meta is result.stability_result.metadata

    assert harness.calls["RecommendationStabilityEngine"].cycle_result is result.cycle_result
    assert harness.calls["RecommendationStabilityEngine"].recommendation is result.recommendation
    assert (
        harness.calls["RecommendationStabilityEngine"].confidence_history
        is harness.confidence_history
    )
    assert (
        harness.calls["RecommendationStabilityEngine"].phase_history
        is harness.phase_history
    )
    assert isinstance(result.market_snapshot, MarketSnapshot)
    assert harness.calls["MarketCycleEngine"] is result.market_snapshot
    assert harness.calls["DataHealthEngine"] is result.market_snapshot
    assert isinstance(harness.calls["RecommendationStabilityEngine"], DecisionContext)
    assert harness.calls["RecommendationStabilityEngine"] is result.decision_context
    assert harness.calls["PhaseTransitionEngine"] is result.decision_context
    for institutional_engine in (
        "InstitutionalRadarEngine", "InstitutionalDecisionMatrixEngine",
        "InstitutionalFlowEngine", "InstitutionalConfidenceEngine",
    ):
        assert harness.calls[institutional_engine] is result.decision_context
    for migrated_engine in (
        "PatternRecognitionEngine", "CandleDNAEngine", "SmartCandlestickEngine",
        "InstitutionalStructureEngine", "FalseBreakoutEngine", "EarlyWarningEngine",
        "MarketRegimeEngine", "SmartMoneyIndexEngine", "MarketEnergyEngine",
    ):
        assert harness.calls[migrated_engine] is result.decision_context
    assert result.decision_context.market_snapshot is result.market_snapshot
    assert result.decision_context.cycle_result is result.cycle_result
    assert result.decision_context.decision_history is result.decision_history
    assert result.decision_context.strike_history is result.decision_strike_history
    assert result.decision_context.engine_results["institutional_radar"] is result.radar_result
    assert result.decision_context.engine_results["institutional_decision_matrix"] is result.decision_matrix_result
    assert result.decision_context.engine_results["institutional_flow"] is result.flow_result
    assert result.decision_context.engine_results["institutional_confidence"] is result.ice_result
    assert harness.calls["SignalValidationEngine"]["ice_result"] is result.ice_result
    assert result.decision_context.engine_results["signal_validation"] is result.validation_result
    assert result.decision_context.engine_results["recommendation_stability"] is result.stability_result
    assert result.decision_context.engine_results["false_breakout"] is result.false_breakout_result
    assert result.decision_context.engine_results["institutional_confirmation"] is result.confirmation_result
    assert isinstance(harness.calls["DataHealthEngine"], MarketSnapshot)
    assert harness.calls["MarketCycleEngine"] is harness.calls["DataHealthEngine"]
    assert harness.calls["DataHealthEngine"].option_result is harness.option_result
    assert harness.calls["DataHealthEngine"].historical_candles is state["historical_pattern_candles"]
    assert harness.calls["DataHealthEngine"].selected_instrument == "TEST"
    assert result.market_snapshot is harness.calls["DataHealthEngine"]
    assert harness.calls["MarketCycleEngine.init"][1]["institutional_compatibility"] is None
    assert harness.calls["AITradeEngine"]["decision_matrix_result"] is result.decision_matrix_result
    assert harness.calls["AITradeEngine"]["trade_plan_result"] is result.trade_plan_result


def test_cached_execution_reuses_analysis_without_acquisition_or_writes(harness):
    class ClientMustNotBeCreated:
        def __init__(self, token):
            raise AssertionError("Upstox client was instantiated for cached execution")

    state = {
        "option_result": harness.option_result,
        "intelligence": harness.intelligence,
        "underlying": "CACHED",
        "expiry": "2026-08-13",
        "historical_pattern_candles": object(),
    }
    result = _execute(
        harness,
        should_load=False,
        state=state,
        client_factory=ClientMustNotBeCreated,
    )

    assert result.option_result is harness.option_result
    assert result.intelligence is harness.intelligence
    assert result.market_snapshot is harness.calls["DataHealthEngine"]
    assert result.market_snapshot is harness.calls["MarketCycleEngine"]
    assert (
        result.market_snapshot.historical_candles
        is state["historical_pattern_candles"]
    )
    forbidden = {
        "acquire_option_chain",
        "normalize_option_chain",
        "acquire_intraday_candles",
        "acquire_historical_candles",
        "save_snapshot",
        "save_phase_history",
        "save_stability_history",
        "save_confidence_history",
        "sync_trade_history",
    }
    assert forbidden.isdisjoint(harness.events)


@pytest.mark.parametrize("veto_engine", ["FalseBreakoutEngine", "SignalValidationEngine"])
def test_safety_veto_cannot_be_restored_by_later_engines(harness, veto_engine):
    if veto_engine == "FalseBreakoutEngine":
        harness.results[veto_engine].metadata["blocked"] = True
    else:
        harness.results[veto_engine].metadata["validated"] = False
        harness.results[veto_engine].metadata.update(passed=2, total=6)

    result = _execute(harness)

    assert result.recommendation["confirmed"] is False
    assert result.recommendation["status"].startswith(("WAIT", "WATCH"))
    assert harness.events.index(veto_engine) < harness.events.index("AITradeEngine")
    assert result.recommendation["status"] != "BUY CE"
    assert harness.calls["AITradeEngine"]["recommendation"]["confirmed"] is False
    assert result.ai_trade_opportunity["decision"] == "WAIT"


def test_critical_acquisition_failure_never_builds_or_emits_buy(harness, monkeypatch):
    def fail_acquisition(*args, **kwargs):
        raise RuntimeError("option chain unavailable")

    monkeypatch.setattr(harness.Client, "get_option_chain", fail_acquisition)

    with pytest.raises(RuntimeError, match="option chain unavailable"):
        _execute(harness, state={})

    assert "build_recommendation" not in harness.events
    assert "AITradeEngine" not in harness.events


def test_critical_pipeline_failure_propagates_before_ai_or_persistence(harness):
    class FailingPipeline:
        def execute(self, context):
            harness.events.append("pipeline_failure")
            raise RuntimeError("critical engine failed")

    service = DashboardApplicationService(
        client_factory=harness.Client,
        store_factory=harness.Store,
        pipeline_factory=FailingPipeline,
    )
    with pytest.raises(RuntimeError, match="critical engine failed"):
        service.execute(
            token="token", instrument_key="NSE|TEST", underlying="TEST",
            expiry="2026-08-06", timeframe=5, strikes=8,
            save_snapshots=True, history_hours=8, should_load=True,
            session_state={},
        )

    assert "AITradeEngine" not in harness.events
    assert "save_phase_history" not in harness.events


def test_incomplete_cached_data_never_builds_or_emits_buy(harness):
    with pytest.raises(DashboardDataUnavailable):
        _execute(harness, should_load=False, state={"option_result": harness.option_result})

    assert "build_recommendation" not in harness.events
    assert "AITradeEngine" not in harness.events


def test_unavailable_candles_force_safe_wait_and_unhealthy_data(harness, monkeypatch):
    warnings = []
    from engines.data_health_engine import DataHealthEngine as RealDataHealthEngine

    monkeypatch.setattr(service_module, "DataHealthEngine", RealDataHealthEngine)
    monkeypatch.setattr(pipeline_module, "DataHealthEngine", RealDataHealthEngine)

    class EmptyCandleClient(harness.Client):
        def get_intraday_candles(self, *args, **kwargs):
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])

    result = DashboardApplicationService(
        client_factory=EmptyCandleClient,
        store_factory=harness.Store,
        warning=warnings.append,
        clock=lambda: "10:11:12",
    ).execute(
        token="token", instrument_key="NSE_INDEX|Nifty 50", underlying="NIFTY",
        expiry="2026-08-06", timeframe=5, strikes=8, save_snapshots=True,
        history_hours=8, should_load=True, session_state={},
    )

    assert result.data_unavailable is True
    assert result.recommendation["side"] == "WAIT"
    assert result.recommendation["confirmed"] is False
    assert result.data_health_result.vote == "BLOCK"
    assert "CANDLES_UNAVAILABLE" in result.data_health_result.metadata["flags"]
    assert warnings and "forced to WAIT" in warnings[0]
    assert "build_recommendation" not in harness.events
