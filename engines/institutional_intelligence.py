from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from .base_engine import BaseEngine, EngineResult
from itos_platform import DecisionContext, MarketSnapshot


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


def _side_vote(value: str) -> str:
    value = str(value or "").upper()
    if "CE" in value or "BULL" in value:
        return "CE"
    if "PE" in value or "BEAR" in value:
        return "PE"
    return "WAIT"


class PhaseTransitionEngine(BaseEngine):
    name = "Phase Transition"

    _next = {
        "Compression": ("Accumulation / Distribution", "WAIT"),
        "Accumulation": ("Bullish Expansion", "CE"),
        "Manipulation": ("Directional Reversal / Expansion", "WAIT"),
        "Bullish Expansion": ("Distribution", "CE"),
        "Distribution": ("Bearish Expansion", "PE"),
        "Bearish Expansion": ("Compression / Accumulation", "PE"),
        "Unknown": ("Unknown", "WAIT"),
    }

    def analyze(
        self, market_data: DecisionContext | Mapping[str, Any]
    ) -> EngineResult:
        context = self._adapt_input(market_data)
        cycle = context.cycle_result
        cycle_metadata = getattr(cycle, "metadata", {})
        meta = (
            cycle_metadata
            if isinstance(cycle_metadata, Mapping) and cycle_metadata
            else context.runtime_configuration.get("cycle", {})
        )
        meta = meta if isinstance(meta, Mapping) else {}
        probabilities = meta.get("probabilities", {}) or {}
        probabilities = probabilities if isinstance(probabilities, Mapping) else {}
        current = str(meta.get("phase", "Unknown"))
        ordered = sorted(probabilities.items(), key=lambda x: _num(x[1]), reverse=True)
        lead = _num(ordered[0][1]) if ordered else 0.0
        runner = _num(ordered[1][1]) if len(ordered) > 1 else 0.0
        gap = max(lead - runner, 0.0)
        next_phase, vote = self._next.get(current, ("Unknown", "WAIT"))
        transition_probability = _clip(45 + (runner * 0.55) + max(8 - gap, 0) * 2.2)
        if current in {"Bullish Expansion", "Bearish Expansion"}:
            transition_probability = _clip(30 + runner * 0.45)
        state = "TRANSITIONING" if gap < 5 else "DEVELOPING" if gap < 12 else "ESTABLISHED"
        explanation = [
            f"{current} leads the phase model at {lead:.1f}%.",
            f"The gap to the second-ranked phase is {gap:.1f} points, classified as {state.lower()}.",
            f"The normal next-stage path is {next_phase}.",
        ]
        return EngineResult(self.name, transition_probability, vote, explanation, {
            "current_phase": current,
            "next_phase": next_phase,
            "transition_probability": transition_probability,
            "transition_state": state,
            "phase_gap": gap,
        })

    @staticmethod
    def _adapt_input(
        market_data: DecisionContext | Mapping[str, Any],
    ) -> DecisionContext:
        """Normalize typed and legacy calls before running the shared calculation."""

        if isinstance(market_data, DecisionContext):
            return market_data

        snapshot = market_data.get("market_snapshot")
        if not isinstance(snapshot, MarketSnapshot):
            snapshot = MarketSnapshot.from_legacy(market_data)
        cycle_result = market_data.get("cycle_result")
        engine_results = dict(market_data.get("engine_results") or {})
        if cycle_result is not None:
            engine_results.setdefault("market_cycle", cycle_result)
        return DecisionContext(
            market_snapshot=snapshot,
            recommendation=market_data.get("recommendation") or {},
            engine_results=engine_results,
            runtime_configuration={"cycle": market_data.get("cycle", {})},
        )


class PatternRecognitionEngine(BaseEngine):
    name = "Pattern Recognition"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        rec = market_data.get("recommendation", {})
        intelligence = market_data.get("intelligence", {})
        option = market_data.get("option_result", {})
        institutional = market_data.get("institutional") or {}
        cycle = market_data.get("cycle_result")
        cycle_meta = getattr(cycle, "metadata", {}) or {}
        price = intelligence.get("price", {})
        summary = option.get("summary", {})

        side = str(rec.get("side", "WAIT"))
        close = _num(price.get("close"))
        vwap = _num(price.get("vwap"), close)
        ema9 = _num(price.get("ema9"), close)
        ema21 = _num(price.get("ema21"), close)
        rvol = _num(rec.get("regime", {}).get("relative_volume"), _num(cycle_meta.get("relative_volume"), 1.0))
        call_change = _num(summary.get("call_oi_change"))
        put_change = _num(summary.get("put_oi_change"))
        flow = _num(institutional.get("primary_strength"))
        phase = str(cycle_meta.get("phase", "Unknown"))
        manipulation = _num(cycle_meta.get("manipulation_score"))

        patterns: list[dict[str, Any]] = []
        def add(name: str, direction: str, confidence: float, evidence: str, invalidation: str) -> None:
            patterns.append({"name": name, "direction": direction, "confidence": round(_clip(confidence), 1), "evidence": evidence, "invalidation": invalidation})

        if close >= vwap and ema9 >= ema21:
            add("VWAP Trend Reclaim", "CE", 55 + min(rvol, 2) * 12, "Price is above VWAP with bullish EMA alignment", "Close below VWAP")
        elif close < vwap and ema9 < ema21:
            add("VWAP Trend Rejection", "PE", 55 + min(rvol, 2) * 12, "Price is below VWAP with bearish EMA alignment", "Close above VWAP")
        if put_change > abs(call_change) * 1.05 and put_change > 0:
            add("Put Writing", "CE", 55 + min(abs(put_change) / max(abs(call_change) + abs(put_change), 1) * 35, 35), "Put OI addition is stronger than call-side addition", "Put OI starts unwinding")
        if call_change > abs(put_change) * 1.05 and call_change > 0:
            add("Call Writing", "PE", 55 + min(abs(call_change) / max(abs(call_change) + abs(put_change), 1) * 35, 35), "Call OI addition is stronger than put-side addition", "Call OI starts unwinding")
        if phase == "Compression" and rvol >= 1.25:
            add("Compression Breakout Watch", _side_vote(side), 58 + (rvol - 1.0) * 18, "Compression is accompanied by expanding participation", "Relative volume falls below 1.0×")
        if phase == "Accumulation":
            add("Wyckoff Accumulation", "CE", 60 + max(flow, 0) * 0.15, "Cycle engine detects accumulation and positive institutional flow", "Distribution probability overtakes accumulation")
        if phase == "Distribution":
            add("Wyckoff Distribution", "PE", 60 + max(-flow, 0) * 0.15, "Cycle engine detects distribution and negative institutional flow", "Accumulation probability overtakes distribution")
        if phase in {"Bullish Expansion", "Bearish Expansion"}:
            add("Directional Expansion", "CE" if phase.startswith("Bullish") else "PE", 68 + min(rvol, 2.0) * 10, f"{phase} is active with {rvol:.2f}× relative volume", "Expansion phase ends or VWAP direction reverses")
        if manipulation >= 55:
            add("Liquidity Sweep / Trap Risk", "BLOCK", manipulation, "Long-wick/high-participation behaviour raised manipulation risk", "Manipulation score falls below 40")

        patterns.sort(key=lambda x: x["confidence"], reverse=True)
        primary = patterns[0] if patterns else {"name": "No High-Quality Pattern", "direction": "WAIT", "confidence": 20.0, "evidence": "Signals are mixed or incomplete", "invalidation": "Wait for alignment"}
        supporting = [p for p in patterns[1:] if p["direction"] == primary["direction"]][:4]
        conflicts = [p for p in patterns if p["direction"] not in {primary["direction"], "BLOCK", "WAIT"}][:4]
        vote = "WAIT" if primary["direction"] in {"WAIT", "BLOCK"} else primary["direction"]
        explanation = [primary["evidence"]]
        if supporting:
            explanation.append(f"{len(supporting)} supporting pattern(s) agree with the primary direction")
        if conflicts:
            explanation.append(f"{len(conflicts)} conflicting pattern(s) reduce conviction")
        return EngineResult(self.name, _num(primary["confidence"]), vote, explanation, {
            "primary_pattern": primary,
            "patterns": patterns,
            "supporting_patterns": supporting,
            "conflicting_patterns": conflicts,
        })


class TradeReadinessEngine(BaseEngine):
    name = "Trade Readiness"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        rec = market_data.get("recommendation", {})
        cycle = market_data.get("cycle_result")
        stability = market_data.get("stability_result")
        pattern = market_data.get("pattern_result")
        cm = getattr(cycle, "metadata", {}) or {}
        sm = getattr(stability, "metadata", {}) or {}
        pm = getattr(pattern, "metadata", {}) or {}
        side = str(rec.get("side", "WAIT"))
        component_scores = rec.get("component_scores", {}) or {}
        consensus = rec.get("confidence_detail", {}).get("consensus", {}) or {}

        checks = [
            ("Base setup", _num(rec.get("model_probability")), _num(rec.get("model_probability")) >= 60, "Model setup score must be at least 60"),
            ("Calibrated confidence", _num(rec.get("confidence")), _num(rec.get("confidence")) >= 70, "Confidence must mature above 70%"),
            ("Trade quality", _num(rec.get("trade_quality")), _num(rec.get("trade_quality")) >= 65, "Trade quality must be at least 65"),
            ("Market cycle", _num(cm.get("phase_confidence")), bool(cm.get("trade_allowed")), "Directional expansion must confirm"),
            ("Stability", _num(sm.get("stability_score")), bool(sm.get("passed")), "Stability must reach 70/100"),
            ("Pattern alignment", _num(getattr(pattern, "score", 0)), getattr(pattern, "vote", "WAIT") in {side, "WAIT"}, "Primary pattern must not oppose the trade"),
            ("Consensus", _num(consensus.get("agreement_ratio"), 0) * 100 if _num(consensus.get("agreement_ratio")) <= 1 else _num(consensus.get("agreement_ratio")), _num(consensus.get("agreeing")) >= max(3, _num(consensus.get("total")) * 0.55), "Most engines must agree"),
            ("Manipulation control", 100 - _num(cm.get("manipulation_score")), _num(cm.get("manipulation_score")) < 55, "Manipulation risk must remain below 55"),
        ]
        weights = [0.15, 0.18, 0.12, 0.16, 0.14, 0.10, 0.08, 0.07]
        score = sum(_clip(item[1]) * weight for item, weight in zip(checks, weights))
        missing = [item[3] for item in checks if not item[2]]
        passed = sum(1 for item in checks if item[2])
        status = "READY" if score >= 80 and not missing else "PREPARE" if score >= 65 else "WAIT"
        vote = side if status == "READY" and side in {"CE", "PE"} else "WAIT"
        return EngineResult(self.name, score, vote, [f"{passed} of {len(checks)} readiness controls are healthy"] + ([f"Waiting for: {missing[0]}"] if missing else ["All readiness controls passed"]), {
            "readiness_score": score,
            "status": status,
            "checks": [{"name": n, "score": round(_clip(s), 1), "passed": ok, "requirement": req} for n, s, ok, req in checks],
            "missing": missing,
        })


class InstitutionalRadarEngine(BaseEngine):
    name = "Institutional Radar"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        rec = market_data.get("recommendation", {})
        option = market_data.get("option_result", {})
        institutional = market_data.get("institutional") or {}
        intelligence = market_data.get("intelligence", {})
        summary = option.get("summary", {})
        side = str(rec.get("side", "WAIT"))
        call_change = _num(summary.get("call_oi_change"))
        put_change = _num(summary.get("put_oi_change"))
        total = max(abs(call_change) + abs(put_change), 1.0)
        flow = _num(institutional.get("primary_strength"))
        bull = _num(intelligence.get("bullish_probability"), 50)
        bear = _num(intelligence.get("bearish_probability"), 50)
        buying = _clip((bull * 0.55) + max(flow, 0) * 0.35 + max(put_change, 0) / total * 35)
        selling = _clip((bear * 0.55) + max(-flow, 0) * 0.35 + max(call_change, 0) / total * 35)
        call_writing = _clip(max(call_change, 0) / total * 100)
        put_writing = _clip(max(put_change, 0) / total * 100)
        bias = "Bullish" if buying > selling + 8 else "Bearish" if selling > buying + 8 else "Neutral"
        score = max(buying, selling)
        vote = "CE" if bias == "Bullish" else "PE" if bias == "Bearish" else "WAIT"
        return EngineResult(self.name, score, vote, [f"Institutional bias is {bias.lower()}", f"Buying pressure {buying:.0f} versus selling pressure {selling:.0f}"], {
            "buying_pressure": buying,
            "selling_pressure": selling,
            "call_writing": call_writing,
            "put_writing": put_writing,
            "institution_bias": bias,
            "recommendation_alignment": vote in {side, "WAIT"},
        })


class MarketStoryEngine(BaseEngine):
    name = "Institutional Market Story"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        rec = market_data.get("recommendation", {})
        cycle = market_data.get("cycle_result")
        transition = market_data.get("transition_result")
        readiness = market_data.get("readiness_result")
        radar = market_data.get("radar_result")
        pattern = market_data.get("pattern_result")
        cm = getattr(cycle, "metadata", {}) or {}
        tm = getattr(transition, "metadata", {}) or {}
        rm = getattr(readiness, "metadata", {}) or {}
        ram = getattr(radar, "metadata", {}) or {}
        pm = getattr(pattern, "metadata", {}) or {}
        phase = cm.get("phase", "Unknown")
        next_phase = tm.get("next_phase", "Unknown")
        bias = ram.get("institution_bias", "Neutral")
        side = rec.get("side", "WAIT")
        primary = pm.get("primary_pattern", {}).get("name", "no dominant pattern")
        readiness_score = _num(rm.get("readiness_score"))
        blockers = rm.get("missing", [])
        action = "consider the ranked option only after confirmation" if side in {"CE", "PE"} else "remain selective and wait"
        if readiness_score >= 80 and not blockers and rec.get("confirmed"):
            action = f"the {side} setup is trade-ready under the configured controls"
        elif blockers:
            action = f"wait for {blockers[0].lower()}"
        story = (
            f"The market is currently in **{phase}**, with the phase model watching for a transition toward "
            f"**{next_phase}**. Institutional radar is **{bias.lower()}**, and the primary detected pattern is "
            f"**{primary}**. Trade readiness is **{readiness_score:.0f}%**. The system recommends that you {action}."
        )
        risk = _num(cm.get("manipulation_score"))
        risk_text = "high" if risk >= 55 else "moderate" if risk >= 35 else "low"
        story += f" Manipulation risk is **{risk_text} ({risk:.0f}/100)**."
        score = readiness_score
        return EngineResult(self.name, score, side if rec.get("confirmed") else "WAIT", [story], {"story": story, "risk_level": risk_text})
