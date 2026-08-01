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
from engines import (
    CandleDNAEngine, FalseBreakoutEngine, InstitutionalConfirmationEngine,
    InstitutionalFootprintEngine, InstitutionalRadarEngine,
    InstitutionalStructureEngine, MarketCycleEngine, MarketStoryEngine,
    PatternRecognitionEngine, PhaseTransitionEngine,
    RecommendationStabilityEngine, SmartCandlestickEngine,
    TradeReadinessEngine, InstitutionalDecisionMatrixEngine,
    InstitutionalFlowEngine, InstitutionalConfidenceEngine,
    SignalValidationEngine, EarlyWarningEngine, MarketRegimeEngine,
    SmartMoneyIndexEngine, MarketEnergyEngine, DataHealthEngine,
)
from engines.ai_trade_engine import AITradeEngine
from itos_platform.decision_context import DecisionContext, MarketSnapshot


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
    ) -> None:
        self.client_factory = client_factory
        self.store_factory = store_factory
        self.warning = warning or (lambda _message: None)
        self.clock = clock or (lambda: time.strftime("%H:%M:%S"))

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
            institutional=institutional,
            last_refresh=session_state.get("last_refresh", ""),
        )
        cycle_result = MarketCycleEngine().analyze(market_snapshot)
        engine_store = self.store_factory()
        engine_underlying = session_state.get("underlying", underlying)
        engine_expiry = session_state.get("expiry", expiry)
        prior_confidence_history = engine_store.get_confidence_history(engine_underlying, engine_expiry, hours=history_hours)
        prior_phase_history = engine_store.get_phase_history(engine_underlying, engine_expiry, hours=history_hours)
        decision_context = DecisionContext(
            market_snapshot=market_snapshot,
            recommendation=recommendation,
            cycle_result=cycle_result,
            confidence_history=prior_confidence_history,
            phase_history=prior_phase_history,
            runtime={"minimum_stability": 70.0, "history_hours": history_hours},
        )
        stability_result = RecommendationStabilityEngine(minimum_stability=70.0).analyze(decision_context)
        transition_result = PhaseTransitionEngine().analyze({"cycle_result": cycle_result})
        pattern_result = PatternRecognitionEngine().analyze({"recommendation": recommendation, "option_result": option_result, "intelligence": intelligence, "institutional": institutional, "cycle_result": cycle_result})
        readiness_result = TradeReadinessEngine().analyze({"recommendation": recommendation, "cycle_result": cycle_result, "stability_result": stability_result, "pattern_result": pattern_result})
        radar_result = InstitutionalRadarEngine().analyze({"recommendation": recommendation, "option_result": option_result, "intelligence": intelligence, "institutional": institutional})
        story_result = MarketStoryEngine().analyze({"recommendation": recommendation, "cycle_result": cycle_result, "transition_result": transition_result, "readiness_result": readiness_result, "radar_result": radar_result, "pattern_result": pattern_result})
        candle_dna_result = CandleDNAEngine().analyze({"intelligence": intelligence})
        smart_candle_result = SmartCandlestickEngine().analyze({"intelligence": intelligence})
        structure_result = InstitutionalStructureEngine().analyze({"intelligence": intelligence})
        footprint_result = InstitutionalFootprintEngine().analyze({"option_result": option_result, "intelligence": intelligence, "institutional": institutional, "cycle_result": cycle_result})
        false_breakout_result = FalseBreakoutEngine().analyze({"structure_result": structure_result, "candle_dna_result": candle_dna_result, "footprint_result": footprint_result, "cycle_result": cycle_result})
        confirmation_result = InstitutionalConfirmationEngine().analyze({"recommendation": recommendation, "footprint_result": footprint_result, "structure_result": structure_result, "smart_candle_result": smart_candle_result, "candle_dna_result": candle_dna_result, "pattern_result": pattern_result, "cycle_result": cycle_result, "false_breakout_result": false_breakout_result})
        metadata = {
            "phase_transition": transition_result, "patterns": pattern_result,
            "trade_readiness_v71": readiness_result, "institutional_radar": radar_result,
            "market_story": story_result, "candle_dna": candle_dna_result,
            "smart_candles": smart_candle_result, "institutional_structures": structure_result,
            "institutional_footprint": footprint_result, "false_breakout": false_breakout_result,
            "institutional_confirmation": confirmation_result,
        }
        recommendation.update({key: result.metadata for key, result in metadata.items()})
        decision_matrix_result = InstitutionalDecisionMatrixEngine().analyze({"recommendation": recommendation, "intelligence": intelligence, "cycle_result": cycle_result, "footprint_result": footprint_result, "confirmation_result": confirmation_result, "candle_dna_result": candle_dna_result, "pattern_result": pattern_result, "false_breakout_result": false_breakout_result})
        cycle_meta, stability_meta = cycle_result.metadata, stability_result.metadata
        recommendation["market_cycle"] = cycle_meta
        recommendation["stability"] = stability_meta
        cycle_gate = bool(cycle_meta.get("trade_allowed", False)) and cycle_result.vote in {recommendation["side"], "WAIT"}
        if recommendation.get("confirmed") and not cycle_gate:
            recommendation["confirmed"] = False
            recommendation["status"] = f"WATCH {recommendation['side']} — MARKET CYCLE NOT READY"
            recommendation["blockers"] = list(dict.fromkeys(recommendation.get("blockers", []) + [f"Market phase is {cycle_meta.get('phase', 'Unknown')}; directional expansion is required"]))
        if recommendation.get("confirmed") and not bool(stability_meta.get("passed", False)):
            recommendation["confirmed"] = False
            recommendation["status"] = f"WATCH {recommendation['side']} — STABILITY DEVELOPING"
            recommendation["blockers"] = list(dict.fromkeys(recommendation.get("blockers", []) + [f"Recommendation stability is {stability_meta.get('stability_score', 0):.0f}%, below the 70% trigger threshold"]))
        if recommendation.get("confirmed") and false_breakout_result.metadata.get("blocked"):
            recommendation["confirmed"] = False
            recommendation["status"] = f"WAIT {recommendation['side']} — FALSE BREAKOUT RISK"
            recommendation["blockers"] = list(dict.fromkeys(recommendation.get("blockers", []) + [f"False-breakout risk is {false_breakout_result.score:.0f}/100"]))
        if recommendation.get("confirmed") and confirmation_result.metadata.get("status") != "CONFIRMED":
            recommendation["confirmed"] = False
            recommendation["status"] = f"WATCH {recommendation['side']} — INSTITUTIONAL CONFIRMATION {confirmation_result.metadata.get('status', 'DEVELOPING')}"
            recommendation["blockers"] = list(dict.fromkeys(recommendation.get("blockers", []) + [f"Institutional confirmation is {confirmation_result.score:.0f}/100"]))
        self._align_top_five(recommendation)
        flow_result = InstitutionalFlowEngine().analyze({"history": decision_history, "strike_history": decision_strike_history, "recommendation": recommendation, "option_result": option_result})
        ice_result = InstitutionalConfidenceEngine().analyze({"recommendation": recommendation, "flow_result": flow_result, "confirmation_result": confirmation_result, "cycle_result": cycle_result, "candle_dna_result": candle_dna_result, "pattern_result": pattern_result, "decision_matrix_result": decision_matrix_result})
        validation_result = SignalValidationEngine().analyze({"recommendation": recommendation, "flow_result": flow_result, "ice_result": ice_result, "confirmation_result": confirmation_result, "false_breakout_result": false_breakout_result, "stability_result": stability_result})
        early_warning_result = EarlyWarningEngine().analyze({"recommendation": recommendation, "flow_result": flow_result, "ice_result": ice_result, "validation_result": validation_result})
        recommendation.update({"institutional_flow_v77": flow_result.metadata, "institutional_confidence_v77": ice_result.metadata, "signal_validation_v77": validation_result.metadata, "early_warning_v77": early_warning_result.metadata})
        regime_result = MarketRegimeEngine().analyze({"option_result": option_result, "intelligence": intelligence, "flow_result": flow_result, "cycle_result": cycle_result})
        smi_result = SmartMoneyIndexEngine().analyze({"recommendation": recommendation, "flow_result": flow_result, "ice_result": ice_result, "confirmation_result": confirmation_result, "regime_result": regime_result, "stability_result": stability_result, "false_breakout_result": false_breakout_result})
        energy_result = MarketEnergyEngine().analyze({"recommendation": recommendation, "option_result": option_result, "intelligence": intelligence, "flow_result": flow_result})
        recommendation.update({"market_regime_v80": regime_result.metadata, "smart_money_index_v80": smi_result.metadata, "market_energy_v80": energy_result.metadata})
        if recommendation.get("confirmed") and not validation_result.metadata.get("validated", False):
            recommendation["confirmed"] = False
            recommendation["status"] = f"WATCH {recommendation['side']} — FLOW VALIDATION DEVELOPING"
            recommendation["blockers"] = list(dict.fromkeys(recommendation.get("blockers", []) + [f"Version 7.7 validation passed {validation_result.metadata.get('passed', 0)} of {validation_result.metadata.get('total', 6)} controls"]))
            self._align_top_five(recommendation)
        if should_load:
            engine_store.save_phase_history(engine_underlying, engine_expiry, cycle_result)
            engine_store.save_stability_history(engine_underlying, engine_expiry, recommendation["side"], stability_result)
        phase_history = engine_store.get_phase_history(engine_underlying, engine_expiry, hours=history_hours)
        stability_history = engine_store.get_stability_history(engine_underlying, engine_expiry, hours=history_hours)
        confidence_history = pd.DataFrame()
        try:
            confidence_store = self.store_factory()
            if should_load:
                confidence_store.save_confidence_history(engine_underlying, engine_expiry, recommendation)
            confidence_history = confidence_store.get_confidence_history(engine_underlying, engine_expiry, hours=history_hours)
        except Exception as exc:
            self.warning(f"Confidence history could not be updated: {exc}")
        trade_history = pd.DataFrame()
        trade_stats = {"total": 0, "active": 0, "success": 0, "failure": 0, "completed": 0, "success_rate": 0.0, "avg_pnl_percent": 0.0, "avg_winner": 0.0, "avg_loser": 0.0, "profit_factor": 0.0}
        try:
            trade_store = self.store_factory()
            if should_load:
                session_state["trade_sync_result"] = trade_store.sync_trade_history(engine_underlying, engine_expiry, recommendation, option_result["chain"])
            trade_history = trade_store.get_trade_history(engine_underlying, engine_expiry)
            trade_stats = trade_store.trade_statistics(engine_underlying, engine_expiry)
        except Exception as exc:
            self.warning(f"Trade history could not be updated: {exc}")
        trade_plan_result = None
        data_health_result = DataHealthEngine(recommendation=recommendation).analyze(market_snapshot)
        ai_trade_opportunity = AITradeEngine().build(recommendation=recommendation, trade_plan_result=trade_plan_result, decision_matrix_result=decision_matrix_result, regime_result=regime_result, flow_result=flow_result, confidence_history=confidence_history)
        names = locals()
        consumed = "option_result intelligence institutional decision_history decision_strike_history recommendation market_snapshot decision_context cycle_result cycle_meta stability_result stability_meta transition_result pattern_result readiness_result radar_result story_result candle_dna_result smart_candle_result structure_result footprint_result false_breakout_result confirmation_result decision_matrix_result flow_result ice_result validation_result early_warning_result regime_result smi_result energy_result phase_history stability_history confidence_history trade_history trade_stats trade_plan_result data_health_result ai_trade_opportunity".split()
        return DashboardApplicationResult({name: names[name] for name in consumed})

    @staticmethod
    def _align_top_five(recommendation: dict[str, Any]) -> None:
        for key in ("ce_top5", "pe_top5"):
            table = recommendation.get(key)
            if isinstance(table, pd.DataFrame) and not table.empty:
                table = table.copy()
                matching_side = key.startswith(recommendation["side"].lower())
                table["trade_state"] = "TRIGGERED" if recommendation["confirmed"] and matching_side else "WAITING"
                recommendation[key] = table
