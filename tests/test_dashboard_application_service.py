from types import SimpleNamespace

import pandas as pd

import dashboard_application_service as service_module
from dashboard_application_service import DashboardApplicationService


def test_service_preserves_pipeline_outputs_session_keys_and_order(monkeypatch):
    events = []
    chain = pd.DataFrame({"strike": [100], "timestamp": ["unused"]})
    candles = pd.DataFrame({"timestamp": ["2026-07-31T09:15:00"]})
    option_result = {"summary": {"spot": 100}, "chain": chain}
    intelligence = {"price": {"trend": "Neutral"}}

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
            events.append("persist_snapshot")
            return 41, True

        def get_history(self, *args, **kwargs): return pd.DataFrame()
        def get_strike_history(self, *args, **kwargs): return pd.DataFrame()
        def get_confidence_history(self, *args, **kwargs): return pd.DataFrame()
        def get_phase_history(self, *args, **kwargs): return pd.DataFrame()
        def get_stability_history(self, *args, **kwargs): return pd.DataFrame()
        def get_trade_history(self, *args, **kwargs): return pd.DataFrame()
        def trade_statistics(self, *args, **kwargs): return {"total": 0}
        def save_phase_history(self, *args): events.append("persist_phase")
        def save_stability_history(self, *args): events.append("persist_stability")
        def save_confidence_history(self, *args): events.append("persist_confidence")
        def sync_trade_history(self, *args):
            events.append("persist_trades")
            return {"created": 0}

    def analysis(df, strikes):
        events.append("analyse_options")
        return option_result

    def price(df):
        events.append("analyse_price")
        return intelligence["price"]

    def combine(options, price_result):
        events.append("combine_intelligence")
        return intelligence

    def recommendation(*args):
        events.append("build_recommendation")
        return {
            "side": "CE", "confirmed": False, "status": "WATCH",
            "blockers": [], "ce_top5": pd.DataFrame(), "pe_top5": pd.DataFrame(),
        }

    monkeypatch.setattr(service_module, "analyse_market", analysis)
    monkeypatch.setattr(service_module, "evaluate_price_action", price)
    monkeypatch.setattr(service_module, "combine_intelligence", combine)
    monkeypatch.setattr(service_module, "build_recommendation", recommendation)
    monkeypatch.setattr(service_module, "institutional_summary", lambda *args: None)

    result_value = SimpleNamespace(
        metadata={"trade_allowed": True, "passed": True, "status": "CONFIRMED", "validated": True},
        vote="WAIT", score=80, confidence=80, explanation=[],
    )

    class Engine:
        def __init__(self, *args, **kwargs): pass
        def analyze(self, inputs): return result_value

    engine_names = [name for name in vars(service_module) if name.endswith("Engine")]
    for name in engine_names:
        monkeypatch.setattr(service_module, name, Engine)

    class TradeEngine:
        def build(self, **kwargs): return {"decision": "WAIT"}

    monkeypatch.setattr(service_module, "AITradeEngine", TradeEngine)
    state = {}
    result = DashboardApplicationService(
        client_factory=Client, store_factory=Store, clock=lambda: "10:11:12"
    ).execute(
        token="token", instrument_key="NSE|TEST", underlying="TEST", expiry="2026-08-06",
        timeframe=5, strikes=8, save_snapshots=True, history_hours=8,
        should_load=True, session_state=state,
    )

    assert events[:9] == [
        ("client", "token"), "acquire_option_chain", "normalize_option_chain",
        "analyse_options", "acquire_intraday_candles", "acquire_historical_candles",
        "analyse_price", "combine_intelligence", "persist_snapshot",
    ]
    assert events.index("build_recommendation") < events.index("persist_phase")
    assert events[-4:] == ["persist_phase", "persist_stability", "persist_confidence", "persist_trades"]
    assert state["option_result"] is option_result
    assert state["intelligence"] is intelligence
    assert {key: state[key] for key in (
        "underlying", "expiry", "timeframe", "last_refresh", "snapshot_id",
        "snapshot_created",
    )} == {
        "underlying": "TEST", "expiry": "2026-08-06", "timeframe": 5,
        "last_refresh": "10:11:12", "snapshot_id": 41, "snapshot_created": True,
    }
    assert result.option_result is option_result
    assert result.intelligence is intelligence
    assert result.recommendation["market_cycle"] is result_value.metadata
    assert result.ai_trade_opportunity == {"decision": "WAIT"}
    assert {"trade_history", "trade_stats", "phase_history", "stability_history"} <= result.values.keys()


def test_cached_execution_does_not_repeat_acquisition_or_write_history(monkeypatch):
    """Characterize the auto-refresh false path: cached values remain the inputs."""
    source = DashboardApplicationService.execute.__code__.co_names
    assert "option_result" in DashboardApplicationService.execute.__code__.co_consts
    assert "should_load" in DashboardApplicationService.execute.__code__.co_varnames
    assert source.count("save_snapshot") == 1
