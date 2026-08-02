"""Repository-free orchestration of the existing ITOS decision engines."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any

import pandas as pd

from engines.core_intelligence import (
    MarketEnergyEngine, MarketRegimeEngine, SmartMoneyIndexEngine,
)
from engines.data_health_engine import DataHealthEngine
from engines.institutional_confirmation import (
    CandleDNAEngine, FalseBreakoutEngine, InstitutionalConfirmationEngine,
    InstitutionalFootprintEngine, InstitutionalStructureEngine,
    SmartCandlestickEngine,
)
from engines.institutional_flow import (
    EarlyWarningEngine, InstitutionalConfidenceEngine, InstitutionalFlowEngine,
    SignalValidationEngine,
)
from engines.institutional_intelligence import (
    InstitutionalRadarEngine, MarketStoryEngine, PatternRecognitionEngine,
    PhaseTransitionEngine, TradeReadinessEngine,
)
from engines.market_cycle_engine import MarketCycleEngine
from engines.stability_engine import RecommendationStabilityEngine
from engines.trade_planner import InstitutionalDecisionMatrixEngine
from .decision_context import DecisionContext
from .institutional_metrics import InstitutionalMetrics, InstitutionalMetricsEngine
from .market_location import MarketLocation, MarketLocationEngine
from .volume_structure import VolumeStructure, VolumeStructureEngine
from .positioning_intelligence import PositioningIntelligence, PositioningIntelligenceEngine
from .compression_intelligence import CompressionIntelligence, CompressionIntelligenceEngine
from .manipulation_intelligence import ManipulationIntelligence, ManipulationIntelligenceEngine
from .institutional_evidence import InstitutionalEvidence, InstitutionalEvidenceEngine
from .decision_confidence import DecisionConfidence, DecisionConfidenceEngine
from .decision_confidence_validation import (
    DecisionConfidenceValidation, DecisionConfidenceValidationEngine,
)
from .trade_opportunity_ranking import (
    TradeOpportunityRanking, TradeOpportunityRankingEngine,
)
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
    market_location: MarketLocation
    volume_structure: VolumeStructure
    positioning_intelligence: PositioningIntelligence
    compression_intelligence: CompressionIntelligence
    footprint_result: Any
    false_breakout_result: Any
    manipulation_intelligence: ManipulationIntelligence
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
    decision_context: DecisionContext
    safety_decision: SafetyDecision
    institutional_metrics: InstitutionalMetrics | None = None
    institutional_evidence: InstitutionalEvidence | None = None
    decision_confidence: DecisionConfidence | None = None
    decision_confidence_validation: DecisionConfidenceValidation | None = None
    trade_opportunity_ranking: TradeOpportunityRanking | None = None

    @property
    def ice_result(self) -> Any:
        return self.institutional_confidence_result

    @property
    def smi_result(self) -> Any:
        return self.smart_money_result

    def dashboard_values(self) -> dict[str, Any]:
        """Return the temporary legacy-name mapping used by the application layer."""
        values = {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name not in {"decision_context", "safety_decision"}
        }
        values.update(ice_result=self.ice_result, smi_result=self.smi_result)
        return values


class DecisionPipeline:
    """Execute each existing engine once, in its characterized order."""

    ENGINE_ORDER = (
        "InstitutionalMetricsEngine",
        "MarketCycleEngine", "RecommendationStabilityEngine", "PhaseTransitionEngine",
        "PatternRecognitionEngine", "TradeReadinessEngine", "InstitutionalRadarEngine",
        "MarketStoryEngine", "CandleDNAEngine", "SmartCandlestickEngine",
        "InstitutionalStructureEngine", "MarketLocationEngine",
        "VolumeStructureEngine",
        "PositioningIntelligenceEngine",
        "CompressionIntelligenceEngine",
        "InstitutionalFootprintEngine",
        "FalseBreakoutEngine", "ManipulationIntelligenceEngine", "InstitutionalConfirmationEngine",
        "InstitutionalDecisionMatrixEngine", "InstitutionalFlowEngine",
        "InstitutionalConfidenceEngine", "SignalValidationEngine", "EarlyWarningEngine",
        "MarketRegimeEngine", "InstitutionalEvidenceEngine", "SmartMoneyIndexEngine",
        "MarketEnergyEngine", "DataHealthEngine", "DecisionConfidenceEngine",
        "DecisionConfidenceValidationEngine",
        "TradeOpportunityRankingEngine",
    )

    def __init__(
        self,
        safety_policy: SafetyGatePolicy | None = None,
        institutional_metrics_engine: InstitutionalMetricsEngine | None = None,
        positioning_intelligence_engine: PositioningIntelligenceEngine | None = None,
        compression_intelligence_engine: CompressionIntelligenceEngine | None = None,
        manipulation_intelligence_engine: ManipulationIntelligenceEngine | None = None,
        institutional_evidence_engine: InstitutionalEvidenceEngine | None = None,
        decision_confidence_engine: DecisionConfidenceEngine | None = None,
        decision_confidence_validation_engine: DecisionConfidenceValidationEngine | None = None,
        trade_opportunity_ranking_engine: TradeOpportunityRankingEngine | None = None,
    ) -> None:
        self.safety_policy = safety_policy or SafetyGatePolicy()
        self.institutional_metrics_engine = (
            institutional_metrics_engine or InstitutionalMetricsEngine()
        )
        self.positioning_intelligence_engine = positioning_intelligence_engine or PositioningIntelligenceEngine()
        self.compression_intelligence_engine = compression_intelligence_engine or CompressionIntelligenceEngine()
        self.manipulation_intelligence_engine = manipulation_intelligence_engine or ManipulationIntelligenceEngine()
        self.institutional_evidence_engine = institutional_evidence_engine or InstitutionalEvidenceEngine()
        self.decision_confidence_engine = decision_confidence_engine or DecisionConfidenceEngine()
        self.decision_confidence_validation_engine = (
            decision_confidence_validation_engine or DecisionConfidenceValidationEngine()
        )
        self.trade_opportunity_ranking_engine = (
            trade_opportunity_ranking_engine or TradeOpportunityRankingEngine()
        )

    def execute(self, context: DecisionContext) -> PipelineResults:
        recommendation = context.recommendation
        snapshot = context.market_snapshot
        institutional_metrics = context.institutional_metrics
        if institutional_metrics is None:
            institutional_metrics = self.institutional_metrics_engine.analyze(context)
        context = replace(context, institutional_metrics=institutional_metrics)

        cycle_result = MarketCycleEngine(
            institutional_compatibility=context.institutional
        ).analyze(snapshot)
        context = self._with_result(
            context, "market_cycle", cycle_result, cycle_result=cycle_result
        )
        stability_result = RecommendationStabilityEngine(
            minimum_stability=70.0
        ).analyze(context)
        context = self._with_result(
            context,
            "recommendation_stability",
            stability_result,
            stability_result=stability_result,
        )
        transition_result = PhaseTransitionEngine().analyze(context)
        context = self._with_result(context, "phase_transition", transition_result)
        pattern_result = PatternRecognitionEngine().analyze(context)
        context = self._with_result(context, "pattern_recognition", pattern_result)
        readiness_result = TradeReadinessEngine().analyze({"recommendation": recommendation, "cycle_result": cycle_result, "stability_result": stability_result, "pattern_result": pattern_result})
        context = self._with_result(context, "trade_readiness", readiness_result)
        radar_result = InstitutionalRadarEngine().analyze(context)
        context = self._with_result(context, "institutional_radar", radar_result)
        story_result = MarketStoryEngine().analyze({"recommendation": recommendation, "cycle_result": cycle_result, "transition_result": transition_result, "readiness_result": readiness_result, "radar_result": radar_result, "pattern_result": pattern_result})
        context = self._with_result(context, "market_story", story_result)
        candle_dna_result = CandleDNAEngine().analyze(context)
        context = self._with_result(context, "candle_dna", candle_dna_result)
        smart_candle_result = SmartCandlestickEngine().analyze(context)
        context = self._with_result(context, "smart_candlestick", smart_candle_result)
        structure_result = InstitutionalStructureEngine().analyze(context)
        context = self._with_result(
            context, "institutional_structure", structure_result
        )
        market_location = MarketLocationEngine().analyze(context)
        context = self._with_result(
            context, "market_location", market_location, market_location=market_location
        )
        volume_structure = VolumeStructureEngine().analyze(context)
        context = self._with_result(
            context, "volume_structure", volume_structure,
            volume_structure=volume_structure,
        )
        positioning_intelligence = self.positioning_intelligence_engine.analyze(context)
        context = self._with_result(
            context, "positioning_intelligence", positioning_intelligence,
            positioning_intelligence=positioning_intelligence,
        )
        compression_intelligence = self.compression_intelligence_engine.analyze(context)
        context = self._with_result(
            context, "compression_intelligence", compression_intelligence,
            compression_intelligence=compression_intelligence,
        )
        footprint_result = InstitutionalFootprintEngine().analyze({"option_result": snapshot.option_result, "intelligence": snapshot.intelligence, "institutional": context.institutional, "cycle_result": cycle_result})
        context = self._with_result(
            context, "institutional_footprint", footprint_result
        )
        false_breakout_result = FalseBreakoutEngine().analyze(context)
        context = self._with_result(
            context,
            "false_breakout",
            false_breakout_result,
            false_breakout_result=false_breakout_result,
        )
        manipulation_intelligence = self.manipulation_intelligence_engine.analyze(context)
        context = self._with_result(
            context, "manipulation_intelligence", manipulation_intelligence,
            manipulation_intelligence=manipulation_intelligence,
        )
        confirmation_result = InstitutionalConfirmationEngine().analyze({"recommendation": recommendation, "footprint_result": footprint_result, "structure_result": structure_result, "smart_candle_result": smart_candle_result, "candle_dna_result": candle_dna_result, "pattern_result": pattern_result, "cycle_result": cycle_result, "false_breakout_result": false_breakout_result})
        context = self._with_result(
            context,
            "institutional_confirmation",
            confirmation_result,
            confirmation_result=confirmation_result,
        )
        metadata = {"phase_transition": transition_result, "patterns": pattern_result, "trade_readiness_v71": readiness_result, "institutional_radar": radar_result, "market_story": story_result, "candle_dna": candle_dna_result, "smart_candles": smart_candle_result, "institutional_structures": structure_result, "institutional_footprint": footprint_result, "false_breakout": false_breakout_result, "institutional_confirmation": confirmation_result}
        recommendation.update({key: result.metadata for key, result in metadata.items()})
        decision_matrix_result = InstitutionalDecisionMatrixEngine().analyze(context)
        context = self._with_result(
            context, "institutional_decision_matrix", decision_matrix_result
        )
        recommendation["market_cycle"] = cycle_result.metadata; recommendation["stability"] = stability_result.metadata
        self.safety_policy.enforce(recommendation, cycle_result=cycle_result, stability_result=stability_result, false_breakout_result=false_breakout_result, confirmation_result=confirmation_result)
        self._align_top_five(recommendation)
        flow_result = InstitutionalFlowEngine().analyze(context)
        context = self._with_result(
            context, "institutional_flow", flow_result, flow_result=flow_result
        )
        institutional_confidence_result = InstitutionalConfidenceEngine().analyze(context)
        context = self._with_result(
            context,
            "institutional_confidence",
            institutional_confidence_result,
            institutional_confidence_result=institutional_confidence_result,
        )
        validation_result = SignalValidationEngine().analyze({"recommendation": recommendation, "flow_result": flow_result, "ice_result": institutional_confidence_result, "confirmation_result": confirmation_result, "false_breakout_result": false_breakout_result, "stability_result": stability_result})
        context = self._with_result(
            context,
            "signal_validation",
            validation_result,
            validation_result=validation_result,
        )
        early_warning_result = EarlyWarningEngine().analyze(context)
        context = self._with_result(context, "early_warning", early_warning_result)
        recommendation.update({"institutional_flow_v77": flow_result.metadata, "institutional_confidence_v77": institutional_confidence_result.metadata, "signal_validation_v77": validation_result.metadata, "early_warning_v77": early_warning_result.metadata})
        regime_result = MarketRegimeEngine().analyze(context)
        context = self._with_result(context, "market_regime", regime_result)
        institutional_evidence = self.institutional_evidence_engine.analyze(context)
        context = self._with_result(
            context, "institutional_evidence", institutional_evidence,
            institutional_evidence=institutional_evidence,
        )
        smart_money_result = SmartMoneyIndexEngine().analyze(context)
        context = self._with_result(context, "smart_money_index", smart_money_result)
        energy_result = MarketEnergyEngine().analyze(context)
        context = self._with_result(context, "market_energy", energy_result)
        recommendation.update({"market_regime_v80": regime_result.metadata, "smart_money_index_v80": smart_money_result.metadata, "market_energy_v80": energy_result.metadata})
        self.safety_policy.enforce(recommendation, validation_result=validation_result)
        self._align_top_five(recommendation)
        data_health_result = DataHealthEngine().analyze(snapshot)
        context = self._with_result(context, "data_health", data_health_result)
        safety_decision = self.safety_policy.enforce(recommendation, data_health_result=data_health_result)
        decision_confidence = self.decision_confidence_engine.analyze(context)
        context = self._with_result(
            context, "decision_confidence", decision_confidence,
            decision_confidence=decision_confidence,
        )
        decision_confidence_validation = self.decision_confidence_validation_engine.analyze(context)
        context = self._with_result(
            context, "decision_confidence_validation", decision_confidence_validation,
            decision_confidence_validation=decision_confidence_validation,
        )
        trade_opportunity_ranking = self.trade_opportunity_ranking_engine.analyze(context)
        context = self._with_result(
            context, "trade_opportunity_ranking", trade_opportunity_ranking,
            trade_opportunity_ranking=trade_opportunity_ranking,
        )
        return PipelineResults(cycle_result, stability_result, transition_result, pattern_result, readiness_result, radar_result, story_result, candle_dna_result, smart_candle_result, structure_result, market_location, volume_structure, positioning_intelligence, compression_intelligence, footprint_result, false_breakout_result, manipulation_intelligence, confirmation_result, decision_matrix_result, flow_result, institutional_confidence_result, validation_result, early_warning_result, regime_result, smart_money_result, energy_result, data_health_result, context, safety_decision, institutional_metrics, institutional_evidence, decision_confidence, decision_confidence_validation, trade_opportunity_ranking)

    @staticmethod
    def _with_result(
        context: DecisionContext, result_name: str, result: Any, **updates: Any
    ) -> DecisionContext:
        """Return a new context containing the completed engine result."""

        engine_results = dict(context.engine_results)
        engine_results[result_name] = result
        return replace(context, engine_results=engine_results, **updates)

    @staticmethod
    def _align_top_five(recommendation: dict[str, Any]) -> None:
        for key in ("ce_top5", "pe_top5"):
            table = recommendation.get(key)
            if isinstance(table, pd.DataFrame) and not table.empty:
                table = table.copy()
                matching_side = key.startswith(str(recommendation.get("side", "WAIT")).lower())
                table["trade_state"] = "TRIGGERED" if recommendation.get("confirmed") and matching_side else "WAITING"
                recommendation[key] = table
