from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, MutableMapping

import pandas as pd

from ai_engine import analyse_market
from market_intelligence import combine_intelligence, evaluate_price_action
from institutional_engine import institutional_summary
from recommendation_engine import build_recommendation
from snapshot_store import SnapshotStore
from upstox_client import UpstoxClient
from engines import DataHealthEngine
from engines.ai_trade_engine import AITradeEngine
from itos_platform.decision_context import (
    DecisionContext, MarketSnapshot, recommendation_is_available,
)
from itos_platform.decision_pipeline import DecisionPipeline


class DashboardDataUnavailable(RuntimeError):
    """Raised when neither an acquisition nor cached dashboard data is available."""


@dataclass(frozen=True)
class DashboardApplicationResult:
    """All application-layer values consumed by the Streamlit dashboard."""

    values: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class DashboardApplicationService:
    """Orchestrates dashboard acquisition, analysis, recommendation and persistence."""

    def __init__(
        self,
        *,
        client_factory: Callable[[str], Any] = UpstoxClient,
        store_factory: Callable[[], Any] = SnapshotStore,
        warning: Callable[[str], None] | None = None,
        clock: Callable[[], str] | None = None,
        pipeline_factory: Callable[[], DecisionPipeline] = DecisionPipeline,
    ) -> None:
        self.client_factory = client_factory
        self.store_factory = store_factory
        self.warning = warning or (lambda _message: None)
        self.clock = clock or (lambda: time.strftime("%H:%M:%S"))
        self.pipeline_factory = pipeline_factory

    def execute(
        self, *, token: str, instrument_key: str, underlying: str, expiry: str,
        timeframe: int, strikes: int, save_snapshots: bool, history_hours: int,
        should_load: bool, session_state: MutableMapping[str, Any],
    ) -> DashboardApplicationResult:
        if should_load:
            client = self.client_factory(token)
            raw_chain = client.get_option_chain(instrument_key, expiry)
            full_df = client.option_chain_to_dataframe(raw_chain)
            option_result = analyse_market(full_df, strikes)
            raw_candles = client.get_intraday_candles(
                instrument_key, interval=timeframe, unit="minutes"
            )
            if raw_candles.empty:
                warning = (
                    "Market candles are unavailable from both Upstox intraday and "
                    "historical feeds. Data health is unhealthy and trading is forced to WAIT."
                )
                self.warning(warning)
                market_snapshot = MarketSnapshot(
                    option_result=option_result, intelligence={},
                    historical_candles=raw_candles,
                    timestamps={"last_refresh": self.clock()},
                    selected_instrument=underlying, expiry=expiry, timeframe=timeframe,
                    data_quality={"recommendation_available": False},
                )
                data_health_result = DataHealthEngine().analyze(market_snapshot)
                recommendation = {
                    "side": "WAIT", "confirmed": False,
                    "status": "WAIT — CANDLE DATA UNAVAILABLE",
                    "blockers": [warning],
                }
                return DashboardApplicationResult({
                    "data_unavailable": True, "warning": warning,
                    "market_snapshot": market_snapshot,
                    "data_health_result": data_health_result,
                    "recommendation": recommendation,
                })
            today = date.today()
            history_from = today - timedelta(days=10)
            try:
                historical_candles = client.get_historical_candles(
                    instrument_key, from_date=history_from.isoformat(),
                    to_date=today.isoformat(), interval=timeframe, unit="minutes",
                )
                combined_pattern_candles = pd.concat(
                    [historical_candles, raw_candles], ignore_index=True
                ).drop_duplicates(subset=["timestamp"], keep="last")
                combined_pattern_candles = combined_pattern_candles.sort_values(
                    "timestamp"
                ).reset_index(drop=True)
            except Exception as history_exc:
                combined_pattern_candles = raw_candles.copy()
                self.warning(
                    "Historical candle pattern data is limited to the current "
                    f"session: {history_exc}"
                )

            price_result = evaluate_price_action(raw_candles)
            intelligence = combine_intelligence(option_result, price_result)
            session_state["option_result"] = option_result
            session_state["intelligence"] = intelligence
            session_state["underlying"] = underlying
            session_state["expiry"] = expiry
            session_state["timeframe"] = timeframe
            session_state["historical_pattern_candles"] = combined_pattern_candles
            session_state["last_refresh"] = self.clock()
            if save_snapshots:
                snapshot_id, created = self.store_factory().save_snapshot(
                    underlying, expiry, option_result, intelligence
                )
                session_state["snapshot_id"] = snapshot_id
                session_state["snapshot_created"] = created

        option_result = session_state.get("option_result")
        intelligence = session_state.get("intelligence")
        if not option_result or not intelligence:
            raise DashboardDataUnavailable

        institutional = None
        decision_history = pd.DataFrame()
        decision_strike_history = pd.DataFrame()
        if save_snapshots:
            try:
                decision_store = self.store_factory()
                decision_underlying = session_state.get("underlying", underlying)
                decision_expiry = session_state.get("expiry", expiry)
                decision_history = decision_store.get_history(decision_underlying, decision_expiry, hours=history_hours)
                decision_strike_history = decision_store.get_strike_history(decision_underlying, decision_expiry, hours=history_hours)
                institutional = institutional_summary(decision_history, decision_strike_history)
            except Exception as exc:
                self.warning(f"Historical flow could not be included in the current recommendation: {exc}")

        recommendation = build_recommendation(option_result, intelligence, institutional)
        market_snapshot = MarketSnapshot(
            option_result=option_result,
            intelligence=intelligence,
            historical_candles=session_state.get(
                "historical_pattern_candles", session_state.get("historical_candles")
            ),
            timestamps={"last_refresh": session_state.get("last_refresh", "")},
            selected_instrument=session_state.get("underlying", underlying),
            expiry=session_state.get("expiry", expiry),
            timeframe=session_state.get("timeframe", timeframe),
            data_quality={
                "recommendation_available": recommendation_is_available(recommendation),
            },
        )
        engine_store = self.store_factory()
        prior_confidence_history = engine_store.get_confidence_history(
            market_snapshot.selected_instrument, market_snapshot.expiry, hours=history_hours
        )
        prior_phase_history = engine_store.get_phase_history(
            market_snapshot.selected_instrument, market_snapshot.expiry, hours=history_hours
        )
        decision_context = DecisionContext(
            market_snapshot=market_snapshot,
            recommendation=recommendation,
            institutional=institutional,
            engine_results={},
            confidence_history=prior_confidence_history,
            phase_history=prior_phase_history,
            decision_history=decision_history,
            strike_history=decision_strike_history,
            runtime_configuration={
                "minimum_stability": 70.0,
                "history_hours": history_hours,
            },
        )
        pipeline_results = self.pipeline_factory().execute(decision_context)
        decision_context = pipeline_results.decision_context
        pipeline_values = pipeline_results.dashboard_values()
        cycle_result = pipeline_results.cycle_result
        stability_result = pipeline_results.stability_result
        decision_matrix_result = pipeline_results.decision_matrix_result
        flow_result = pipeline_results.flow_result
        regime_result = pipeline_results.regime_result
        data_health_result = pipeline_results.data_health_result
        cycle_meta = cycle_result.metadata
        stability_meta = stability_result.metadata
        if should_load:
            engine_store.save_phase_history(
                market_snapshot.selected_instrument, market_snapshot.expiry, cycle_result
            )
            engine_store.save_stability_history(
                market_snapshot.selected_instrument, market_snapshot.expiry,
                recommendation["side"], stability_result,
            )
        phase_history = engine_store.get_phase_history(
            market_snapshot.selected_instrument, market_snapshot.expiry, hours=history_hours
        )
        stability_history = engine_store.get_stability_history(
            market_snapshot.selected_instrument, market_snapshot.expiry, hours=history_hours
        )
        confidence_history = pd.DataFrame()
        try:
            confidence_store = self.store_factory()
            if should_load:
                confidence_store.save_confidence_history(
                    market_snapshot.selected_instrument, market_snapshot.expiry, recommendation
                )
            confidence_history = confidence_store.get_confidence_history(
                market_snapshot.selected_instrument, market_snapshot.expiry,
                hours=history_hours,
            )
        except Exception as exc:
            self.warning(f"Confidence history could not be updated: {exc}")
        trade_history = pd.DataFrame()
        trade_stats = {"total": 0, "active": 0, "success": 0, "failure": 0, "completed": 0, "success_rate": 0.0, "avg_pnl_percent": 0.0, "avg_winner": 0.0, "avg_loser": 0.0, "profit_factor": 0.0}
        try:
            trade_store = self.store_factory()
            if should_load:
                session_state["trade_sync_result"] = trade_store.sync_trade_history(
                    market_snapshot.selected_instrument, market_snapshot.expiry,
                    recommendation, option_result["chain"],
                )
            trade_history = trade_store.get_trade_history(
                market_snapshot.selected_instrument, market_snapshot.expiry
            )
            trade_stats = trade_store.trade_statistics(
                market_snapshot.selected_instrument, market_snapshot.expiry
            )
        except Exception as exc:
            self.warning(f"Trade history could not be updated: {exc}")
        trade_plan_result = None
        ai_trade_opportunity = AITradeEngine().build(recommendation=recommendation, trade_plan_result=trade_plan_result, decision_matrix_result=decision_matrix_result, regime_result=regime_result, flow_result=flow_result, confidence_history=confidence_history)
        values = {
            "market_snapshot": market_snapshot, "decision_context": decision_context,
            "pipeline_results": pipeline_results, "option_result": option_result,
            "intelligence": intelligence, "institutional": institutional,
            "decision_history": decision_history,
            "decision_strike_history": decision_strike_history,
            "recommendation": recommendation, "cycle_meta": cycle_meta,
            "stability_meta": stability_meta, "phase_history": phase_history,
            "stability_history": stability_history,
            "confidence_history": confidence_history, "trade_history": trade_history,
            "trade_stats": trade_stats, "trade_plan_result": trade_plan_result,
            "ai_trade_opportunity": ai_trade_opportunity,
        }
        values.update(pipeline_values)
        return DashboardApplicationResult(values)

    @staticmethod
    def _align_top_five(recommendation: dict[str, Any]) -> None:
        for key in ("ce_top5", "pe_top5"):
            table = recommendation.get(key)
            if isinstance(table, pd.DataFrame) and not table.empty:
                table = table.copy()
                matching_side = key.startswith(recommendation["side"].lower())
                table["trade_state"] = "TRIGGERED" if recommendation["confirmed"] and matching_side else "WAITING"
                recommendation[key] = table
