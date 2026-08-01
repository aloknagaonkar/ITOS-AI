from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from .base_engine import BaseEngine, EngineResult
from itos_platform import DecisionContext


def _context_input(value: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the legacy-shaped, read-only view used by market-state logic."""
    if not isinstance(value, DecisionContext):
        return value if isinstance(value, Mapping) else {}
    snapshot = value.market_snapshot
    results = value.engine_results if isinstance(value.engine_results, Mapping) else {}
    return {
        "option_result": snapshot.option_result if isinstance(snapshot.option_result, Mapping) else {},
        "intelligence": snapshot.intelligence if isinstance(snapshot.intelligence, Mapping) else {},
        "recommendation": value.recommendation if isinstance(value.recommendation, Mapping) else {},
        "cycle_result": value.cycle_result,
        "flow_result": value.flow_result or results.get("institutional_flow"),
        "ice_result": value.institutional_confidence_result or results.get("institutional_confidence"),
        "validation_result": value.validation_result or results.get("signal_validation"),
        "confirmation_result": value.confirmation_result or results.get("institutional_confirmation"),
        "stability_result": value.stability_result or results.get("recommendation_stability"),
        "false_breakout_result": value.false_breakout_result or results.get("false_breakout"),
        "regime_result": results.get("market_regime"),
    }


def _metadata(result: Any) -> Mapping[str, Any]:
    metadata = getattr(result, "metadata", {})
    return metadata if isinstance(metadata, Mapping) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


class MarketRegimeEngine(BaseEngine):
    """Classifies the current session into a practical institutional regime."""

    name = "Market Regime Engine"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        intelligence = market_data.get("intelligence", {}) or {}
        price = intelligence.get("price", {}) or {}
        flow = market_data.get("flow_result")
        cycle = market_data.get("cycle_result")
        summary = (market_data.get("option_result", {}) or {}).get("summary", {}) or {}

        ema9 = _num(price.get("ema9"))
        ema21 = _num(price.get("ema21"))
        vwap = _num(price.get("vwap"))
        spot = _num(summary.get("spot"), _num(price.get("close")))
        atr = max(_num(price.get("atr"), 1.0), 1e-9)
        rsi = _num(price.get("rsi"), 50.0)
        flow_meta = _metadata(flow)
        net_flow = _num(flow_meta.get("net_bullish_flow"))
        acceleration = _num(flow_meta.get("oi_acceleration"))
        iv_expansion = _num(flow_meta.get("iv_expansion"))
        phase = str(_metadata(cycle).get("phase", "Unknown"))

        trend_distance = abs(ema9 - ema21) / atr
        vwap_distance = abs(spot - vwap) / atr
        directional = np.sign((ema9 - ema21) + (spot - vwap))

        scores = {
            "Trend Day": _clip(35 + trend_distance * 22 + vwap_distance * 15 + abs(net_flow) * 0.22),
            "Range Day": _clip(88 - trend_distance * 28 - vwap_distance * 22 - abs(net_flow) * 0.28),
            "Breakout Day": _clip(25 + vwap_distance * 28 + abs(acceleration) * 4 + abs(iv_expansion) * 12),
            "Short Covering": _clip(20 + max(net_flow, 0) * 0.45 + max(rsi - 52, 0) * 1.2 + max(acceleration, 0) * 3),
            "Distribution": _clip(20 + max(-net_flow, 0) * 0.45 + max(48 - rsi, 0) * 1.2 + max(-acceleration, 0) * 3),
            "Accumulation": _clip(25 + max(net_flow, 0) * 0.35 + max(55 - abs(rsi - 50), 0) * 0.5),
            "Volatility Expansion": _clip(25 + abs(iv_expansion) * 22 + vwap_distance * 18 + abs(acceleration) * 3),
        }
        if "Compression" in phase:
            scores["Range Day"] = min(100.0, scores["Range Day"] + 12)
        if "Expansion" in phase:
            scores["Breakout Day"] = min(100.0, scores["Breakout Day"] + 12)

        regime = max(scores, key=scores.get)
        confidence = scores[regime]
        if regime in {"Trend Day", "Breakout Day", "Short Covering", "Accumulation"} and directional > 0:
            vote = "CE"
        elif regime in {"Trend Day", "Breakout Day", "Distribution"} and directional < 0:
            vote = "PE"
        else:
            vote = "WAIT"

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        reasons = [
            f"EMA separation is {trend_distance:.2f} ATR",
            f"Spot is {vwap_distance:.2f} ATR from VWAP",
            f"Net institutional flow is {net_flow:+.1f}",
            f"Existing market-cycle phase is {phase}",
        ]
        return EngineResult(self.name, confidence, vote, reasons, {
            "regime": regime,
            "confidence": round(confidence, 1),
            "direction": "BULLISH" if directional > 0 else "BEARISH" if directional < 0 else "NEUTRAL",
            "rankings": [{"Regime": name, "Score": round(score, 1)} for name, score in ranked],
            "trend_distance_atr": round(trend_distance, 3),
            "vwap_distance_atr": round(vwap_distance, 3),
        })

    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        return _context_input(market_data)


class SmartMoneyIndexEngine(BaseEngine):
    """A compact score summarising multi-engine institutional alignment."""

    name = "Smart Money Index"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        side = str((market_data.get("recommendation", {}) or {}).get("side", "WAIT"))
        flow = market_data.get("flow_result")
        ice = market_data.get("ice_result")
        confirmation = market_data.get("confirmation_result")
        regime = market_data.get("regime_result")
        stability = market_data.get("stability_result")
        false_breakout = market_data.get("false_breakout_result")

        components = [
            ("Institutional Flow", _num(getattr(flow, "score", 0)), 0.24),
            ("ICE Confidence", _num(getattr(ice, "score", 0)), 0.24),
            ("Institutional Confirmation", _num(getattr(confirmation, "score", 0)), 0.18),
            ("Market Regime", _num(getattr(regime, "score", 0)), 0.14),
            ("Stability", _num(getattr(stability, "score", 0)), 0.12),
            ("Breakout Safety", 100 - _num(getattr(false_breakout, "score", 0)), 0.08),
        ]
        score = _clip(sum(value * weight for _, value, weight in components))
        aligned = sum(value >= 65 for _, value, _ in components)
        vote = side if side in {"CE", "PE"} and score >= 72 and aligned >= 4 else "WAIT"
        label = "INSTITUTIONAL GRADE" if score >= 90 else "HIGH CONVICTION" if score >= 80 else "BUILDING" if score >= 65 else "WEAK"
        rows = [{"Component": name, "Score": round(value, 1), "Weight %": round(weight * 100), "Aligned": value >= 65} for name, value, weight in components]
        return EngineResult(self.name, score, vote, [f"{name}: {value:.0f}" for name, value, _ in components], {
            "smi": round(score, 1), "label": label, "aligned": aligned, "total": len(components), "components": rows,
        })

    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        return _context_input(market_data)


class MarketEnergyEngine(BaseEngine):
    """Estimates whether the market has sufficient energy for directional follow-through."""

    name = "Market Energy Engine"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        intelligence = market_data.get("intelligence", {}) or {}
        price = intelligence.get("price", {}) or {}
        flow = market_data.get("flow_result")
        summary = (market_data.get("option_result", {}) or {}).get("summary", {}) or {}
        components = (market_data.get("recommendation", {}) or {}).get("component_scores", {}) or {}

        atr = _num(price.get("atr"), 1.0)
        spot = _num(summary.get("spot"))
        vwap = _num(price.get("vwap"), spot)
        vwap_impulse = min(abs(spot - vwap) / max(atr, 1e-9) * 35, 100)
        flow_meta = _metadata(flow)
        inputs = [
            ("ATR / Price Expansion", _num(components.get("Momentum"), _num(price.get("score"), 50)), 0.22),
            ("Volume Expansion", _num(components.get("Volume"), 50), 0.20),
            ("OI Acceleration", _clip(50 + abs(_num(flow_meta.get("oi_acceleration"))) * 5), 0.20),
            ("IV Expansion", _clip(45 + abs(_num(flow_meta.get("iv_expansion"))) * 20), 0.14),
            ("VWAP Impulse", _clip(vwap_impulse), 0.14),
            ("Gamma Flow", _clip(50 + abs(_num(flow_meta.get("gamma_flow"))) * 14000), 0.10),
        ]
        energy = _clip(sum(value * weight for _, value, weight in inputs))
        state = "EXPLOSIVE" if energy >= 88 else "STRONG" if energy >= 75 else "DEVELOPING" if energy >= 58 else "LOW"
        direction = getattr(flow, "vote", "WAIT") if energy >= 65 else "WAIT"
        return EngineResult(self.name, energy, direction, [f"{name}: {value:.0f}" for name, value, _ in inputs], {
            "energy": round(energy, 1), "state": state,
            "move_potential": "High" if energy >= 75 else "Moderate" if energy >= 58 else "Low",
            "components": [{"Component": n, "Score": round(v, 1), "Weight %": round(w * 100)} for n, v, w in inputs],
        })

    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        return _context_input(market_data)


class OpportunityLifecycleEngine(BaseEngine):
    """Tracks a potential trade through a controlled opportunity lifecycle."""

    name = "Opportunity Lifecycle Engine"
    stages = ["SCANNING", "ACCUMULATION", "VALIDATION", "READY", "ACTIVE TRADE", "MANAGEMENT", "EXIT", "LEARNING"]

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        recommendation = market_data.get("recommendation", {}) or {}
        ice = market_data.get("ice_result")
        validation = market_data.get("validation_result")
        early = market_data.get("early_warning_result")
        smi = market_data.get("smi_result")
        energy = market_data.get("energy_result")
        plan = market_data.get("trade_plan_result")

        side = str(recommendation.get("side", "WAIT"))
        confirmed = bool(recommendation.get("confirmed"))
        validated = bool(getattr(validation, "metadata", {}).get("validated"))
        early_state = str(getattr(early, "metadata", {}).get("state", ""))
        plan_state = str(getattr(plan, "metadata", {}).get("state", "WAIT"))
        score = _clip(np.mean([
            _num(getattr(ice, "score", 0)), _num(getattr(smi, "score", 0)), _num(getattr(energy, "score", 0))
        ]))

        if plan_state == "TRIGGERED" and confirmed and validated:
            stage = "READY"
        elif validated:
            stage = "VALIDATION"
        elif "EARLY" in early_state or score >= 60:
            stage = "ACCUMULATION"
        else:
            stage = "SCANNING"

        next_stage = self.stages[min(self.stages.index(stage) + 1, len(self.stages) - 1)]
        requirements = []
        if stage == "SCANNING":
            requirements = ["ICE ≥ 60", "Directional institutional flow", "Market energy building"]
        elif stage == "ACCUMULATION":
            requirements = ["Pass at least 5/6 validation controls", "Maintain SMI ≥ 72", "No false-breakout block"]
        elif stage == "VALIDATION":
            requirements = ["Final recommendation remains confirmed", "Trade planner state becomes TRIGGERED"]
        elif stage == "READY":
            requirements = ["Trader review", "Risk and lot-size confirmation", "Entry-zone discipline"]

        probability = min(score, 95.0) if side in {"CE", "PE"} else min(score, 55.0)
        return EngineResult(self.name, probability, side if stage in {"VALIDATION", "READY"} else "WAIT", [f"Opportunity stage: {stage}"], {
            "stage": stage, "next_stage": next_stage, "progress": round((self.stages.index(stage) + 1) / len(self.stages) * 100, 1),
            "probability": round(probability, 1), "side": side, "requirements": requirements,
            "lifecycle": [{"Stage": item, "Status": "CURRENT" if item == stage else "COMPLETED" if self.stages.index(item) < self.stages.index(stage) else "PENDING"} for item in self.stages],
        })
