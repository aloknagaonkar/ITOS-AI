"""Repository-free orchestration of the existing ITOS decision engines."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import pandas as pd

from engines import (
    CandleDNAEngine, DataHealthEngine, EarlyWarningEngine, FalseBreakoutEngine,
    InstitutionalConfidenceEngine, InstitutionalConfirmationEngine,
    InstitutionalDecisionMatrixEngine, InstitutionalFlowEngine,
    InstitutionalFootprintEngine, InstitutionalRadarEngine,
    InstitutionalStructureEngine, MarketCycleEngine, MarketEnergyEngine,
    MarketRegimeEngine, MarketStoryEngine, PatternRecognitionEngine,
    PhaseTransitionEngine, RecommendationStabilityEngine, SignalValidationEngine,
    SmartCandlestickEngine, SmartMoneyIndexEngine, TradeReadinessEngine,
)
from .decision_context import DecisionContext
from .safety_gate_policy import SafetyDecision, SafetyGatePolicy


@dataclass(frozen=True)
class PipelineResults:
    cycle_result: Any
    stability_result: Any
    transition_result: Any
    pattern_result: Any
    readiness_result: Any
    radar_result: Any
    story_result: Any
    candle_dna_result: Any
    smart_candle_result: Any
    structure_result: Any
    footprint_result: Any
    false_breakout_result: Any
    confirmation_result: Any
    decision_matrix_result: Any
    flow_result: Any
    institutional_confidence_result: Any
    validation_result: Any
    early_warning_result: Any
    regime_result: Any
    smart_money_result: Any
    energy_result: Any
    data_health_result: Any
    safety_decision: SafetyDecision

    @property
    def ice_result(self) -> Any:
        return self.institutional_confidence_result

    @property
    def smi_result(self) -> Any:
        return self.smart_money_result

    def dashboard_values(self) -> dict[str, Any]:
        """Return the temporary legacy-name mapping used by the application layer."""
        values = {item.name: getattr(self, item.name) for item in fields(self) if item.name != "safety_decision"}
        values.update(ice_result=self.ice_result, smi_result=self.smi_result)
        return values


class DecisionPipeline:
    """Execute each existing engine once, in its characterized order."""

    ENGINE_ORDER = (
        "MarketCycleEngine", "RecommendationStabilityEngine", "PhaseTransitionEngine",
        "PatternRecognitionEngine", "TradeReadinessEngine", "InstitutionalRadarEngine",
        "MarketStoryEngine", "CandleDNAEngine", "SmartCandlestickEngine",
        "InstitutionalStructureEngine", "InstitutionalFootprintEngine",
        "FalseBreakoutEngine", "InstitutionalConfirmationEngine",
        "InstitutionalDecisionMatrixEngine", "InstitutionalFlowEngine",
        "InstitutionalConfidenceEngine", "SignalValidationEngine", "EarlyWarningEngine",
        "MarketRegimeEngine", "SmartMoneyIndexEngine", "MarketEnergyEngine", "DataHealthEngine",
    )

    def __init__(self, safety_policy: SafetyGatePolicy | None = None) -> None:
        self.safety_policy = safety_policy or SafetyGatePolicy()

    def execute(self, context: DecisionContext) -> PipelineResults:
        recommendation = context.recommendation
        snapshot = context.market_snapshot
        store = context.engine_results

        cycle_result = MarketCycleEngine(institutional_compatibility=context.institutional).analyze(snapshot); store["market_cycle"] = cycle_result
        stability_result = RecommendationStabilityEngine(minimum_stability=70.0).analyze(context); store["recommendation_stability"] = stability_result
        transition_result = PhaseTransitionEngine().analyze(context)
        pattern_result = PatternRecognitionEngine().analyze(context); store["pattern_recognition"] = pattern_result
        readiness_result = TradeReadinessEngine().analyze({"recommendation": recommendation, "cycle_result": cycle_result, "stability_result": stability_result, "pattern_result": pattern_result})
        radar_result = InstitutionalRadarEngine().analyze(context); store["institutional_radar"] = radar_result
        story_result = MarketStoryEngine().analyze({"recommendation": recommendation, "cycle_result": cycle_result, "transition_result": transition_result, "readiness_result": readiness_result, "radar_result": radar_result, "pattern_result": pattern_result})
        candle_dna_result = CandleDNAEngine().analyze(context); store["candle_dna"] = candle_dna_result
        smart_candle_result = SmartCandlestickEngine().analyze(context); store["smart_candlestick"] = smart_candle_result
        structure_result = InstitutionalStructureEngine().analyze(context); store["institutional_structure"] = structure_result
        footprint_result = InstitutionalFootprintEngine().analyze({"option_result": snapshot.option_result, "intelligence": snapshot.intelligence, "institutional": context.institutional, "cycle_result": cycle_result}); store["institutional_footprint"] = footprint_result
        false_breakout_result = FalseBreakoutEngine().analyze(context); store["false_breakout"] = false_breakout_result
        confirmation_result = InstitutionalConfirmationEngine().analyze({"recommendation": recommendation, "footprint_result": footprint_result, "structure_result": structure_result, "smart_candle_result": smart_candle_result, "candle_dna_result": candle_dna_result, "pattern_result": pattern_result, "cycle_result": cycle_result, "false_breakout_result": false_breakout_result}); store["institutional_confirmation"] = confirmation_result
        metadata = {"phase_transition": transition_result, "patterns": pattern_result, "trade_readiness_v71": readiness_result, "institutional_radar": radar_result, "market_story": story_result, "candle_dna": candle_dna_result, "smart_candles": smart_candle_result, "institutional_structures": structure_result, "institutional_footprint": footprint_result, "false_breakout": false_breakout_result, "institutional_confirmation": confirmation_result}
        recommendation.update({key: result.metadata for key, result in metadata.items()})
        decision_matrix_result = InstitutionalDecisionMatrixEngine().analyze(context); store["institutional_decision_matrix"] = decision_matrix_result
        recommendation["market_cycle"] = cycle_result.metadata; recommendation["stability"] = stability_result.metadata
        self.safety_policy.enforce(recommendation, cycle_result=cycle_result, stability_result=stability_result, false_breakout_result=false_breakout_result, confirmation_result=confirmation_result)
        self._align_top_five(recommendation)
        flow_result = InstitutionalFlowEngine().analyze(context); store["institutional_flow"] = flow_result
        institutional_confidence_result = InstitutionalConfidenceEngine().analyze(context); store["institutional_confidence"] = institutional_confidence_result
        validation_result = SignalValidationEngine().analyze({"recommendation": recommendation, "flow_result": flow_result, "ice_result": institutional_confidence_result, "confirmation_result": confirmation_result, "false_breakout_result": false_breakout_result, "stability_result": stability_result}); store["signal_validation"] = validation_result
        early_warning_result = EarlyWarningEngine().analyze(context); store["early_warning"] = early_warning_result
        recommendation.update({"institutional_flow_v77": flow_result.metadata, "institutional_confidence_v77": institutional_confidence_result.metadata, "signal_validation_v77": validation_result.metadata, "early_warning_v77": early_warning_result.metadata})
        regime_result = MarketRegimeEngine().analyze(context); store["market_regime"] = regime_result
        smart_money_result = SmartMoneyIndexEngine().analyze(context); store["smart_money_index"] = smart_money_result
        energy_result = MarketEnergyEngine().analyze(context); store["market_energy"] = energy_result
        recommendation.update({"market_regime_v80": regime_result.metadata, "smart_money_index_v80": smart_money_result.metadata, "market_energy_v80": energy_result.metadata})
        self.safety_policy.enforce(recommendation, validation_result=validation_result)
        self._align_top_five(recommendation)
        data_health_result = DataHealthEngine().analyze(snapshot); store["data_health"] = data_health_result
        safety_decision = self.safety_policy.enforce(recommendation, data_health_result=data_health_result)
        return PipelineResults(cycle_result, stability_result, transition_result, pattern_result, readiness_result, radar_result, story_result, candle_dna_result, smart_candle_result, structure_result, footprint_result, false_breakout_result, confirmation_result, decision_matrix_result, flow_result, institutional_confidence_result, validation_result, early_warning_result, regime_result, smart_money_result, energy_result, data_health_result, safety_decision)

    @staticmethod
    def _align_top_five(recommendation: dict[str, Any]) -> None:
        for key in ("ce_top5", "pe_top5"):
            table = recommendation.get(key)
            if isinstance(table, pd.DataFrame) and not table.empty:
                table = table.copy()
                matching_side = key.startswith(str(recommendation.get("side", "WAIT")).lower())
                table["trade_state"] = "TRIGGERED" if recommendation.get("confirmed") and matching_side else "WAITING"
                recommendation[key] = table
