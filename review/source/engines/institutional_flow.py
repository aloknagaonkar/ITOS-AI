from __future__ import annotations

from dataclasses import asdict
from collections.abc import Mapping
from typing import Any
import numpy as np
import pandas as pd

from .base_engine import BaseEngine, EngineResult
from itos_platform import DecisionContext


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if np.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


def _slope(series: pd.Series, periods: int = 5) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna().tail(periods)
    if len(s) < 2:
        return 0.0
    x = np.arange(len(s), dtype=float)
    return float(np.polyfit(x, s.to_numpy(dtype=float), 1)[0])


def _acceleration(series: pd.Series, periods: int = 7) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna().tail(periods)
    if len(s) < 4:
        return 0.0
    first = s.diff().dropna()
    return _slope(first, min(5, len(first)))


class InstitutionalFlowEngine(BaseEngine):
    """Measure the direction, velocity and acceleration of options positioning."""

    name = "Institutional Flow Engine"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        history = market_data.get("history")
        strike_history = market_data.get("strike_history")
        recommendation = market_data.get("recommendation", {})
        side = str(recommendation.get("side", "WAIT"))

        if not isinstance(history, pd.DataFrame) or history.empty:
            return EngineResult(self.name, 25, "WAIT", ["Flow needs stored minute snapshots"], {
                "flow_state": "WARMING UP", "snapshot_count": 0, "minimum_snapshots": 4,
                "call_flow_score": 50.0, "put_flow_score": 50.0, "net_bullish_flow": 0.0,
                "oi_momentum": 0.0, "oi_acceleration": 0.0, "delta_flow": 0.0,
                "gamma_wall": None, "iv_expansion": 0.0, "timeline": [], "heatmap": [],
            })

        required_history = {
            "captured_at", "call_oi", "put_oi", "spot", "atm_iv", "pcr_oi",
            "call_oi_change", "put_oi_change",
        }
        if not required_history.issubset(history.columns):
            return EngineResult(self.name, 25, "WAIT", ["Flow needs stored minute snapshots"], {
                "flow_state": "WARMING UP", "snapshot_count": 0, "minimum_snapshots": 4,
                "call_flow_score": 50.0, "put_flow_score": 50.0, "net_bullish_flow": 0.0,
                "oi_momentum": 0.0, "oi_acceleration": 0.0, "delta_flow": 0.0,
                "gamma_wall": None, "iv_expansion": 0.0, "timeline": [], "heatmap": [],
            })

        h = history.sort_values("captured_at").copy()
        n = len(h)
        call_change = _slope(h["call_oi"], 6)
        put_change = _slope(h["put_oi"], 6)
        call_accel = _acceleration(h["call_oi"], 8)
        put_accel = _acceleration(h["put_oi"], 8)
        spot_slope = _slope(h["spot"], 6)
        iv_slope = _slope(h["atm_iv"], 6)
        pcr_slope = _slope(h["pcr_oi"], 6)

        scale = max(abs(call_change), abs(put_change), 1.0)
        put_flow = _clip(50 + (put_change / scale) * 25 + (put_accel / max(abs(call_accel), abs(put_accel), 1.0)) * 15 + np.sign(spot_slope) * 10)
        call_flow = _clip(50 + (call_change / scale) * 25 + (call_accel / max(abs(call_accel), abs(put_accel), 1.0)) * 15 - np.sign(spot_slope) * 10)
        bullish_flow = _clip(50 + (put_flow - call_flow) * .62 + np.tanh(pcr_slope * 8) * 15 + np.sign(spot_slope) * 10)
        bearish_flow = 100 - bullish_flow
        chosen = bullish_flow if side == "CE" else bearish_flow if side == "PE" else max(bullish_flow, bearish_flow)

        delta_flow = gamma_flow = 0.0
        gamma_wall = None
        heatmap: list[dict[str, Any]] = []
        strike_columns = {
            "captured_at", "strike", "call_oi", "put_oi", "call_delta",
            "put_delta", "call_gamma", "put_gamma",
        }
        if (
            isinstance(strike_history, pd.DataFrame)
            and not strike_history.empty
            and strike_columns.issubset(strike_history.columns)
        ):
            sh = strike_history.sort_values(["captured_at", "strike"]).copy()
            latest_time = sh["captured_at"].max()
            latest = sh[sh["captured_at"] == latest_time].copy()
            if not latest.empty:
                latest["total_oi"] = latest["call_oi"] + latest["put_oi"]
                latest["gamma_exposure"] = (
                    latest["call_gamma"].abs() * latest["call_oi"] + latest["put_gamma"].abs() * latest["put_oi"]
                )
                wall = latest.sort_values("gamma_exposure", ascending=False).head(1)
                if not wall.empty:
                    w = wall.iloc[0]
                    gamma_wall = {"strike": float(w["strike"]), "strength": _clip(45 + float(w["gamma_exposure"]) / max(float(latest["gamma_exposure"].median()), 1) * 12)}
                top = latest.nlargest(12, "total_oi")
                max_oi = max(float(top["total_oi"].max()), 1)
                heatmap = [{
                    "Strike": float(r.strike), "Call OI": float(r.call_oi), "Put OI": float(r.put_oi),
                    "Total OI": float(r.total_oi), "Intensity": round(float(r.total_oi) / max_oi * 100, 1),
                    "Dominance": "PUT" if r.put_oi > r.call_oi else "CALL",
                } for r in top.sort_values("strike").itertuples(index=False)]

            grouped = sh.groupby("captured_at", as_index=False).agg(
                call_delta=("call_delta", "mean"), put_delta=("put_delta", "mean"),
                call_gamma=("call_gamma", "mean"), put_gamma=("put_gamma", "mean"),
            )
            delta_flow = _slope(grouped["call_delta"].abs(), 6) - _slope(grouped["put_delta"].abs(), 6)
            gamma_flow = _slope(grouped["call_gamma"].abs(), 6) - _slope(grouped["put_gamma"].abs(), 6)

        timeline = []
        tail = h.tail(20)
        previous_bias = None
        for row in tail.itertuples(index=False):
            bias = "PUT WRITING" if _num(row.put_oi_change) > _num(row.call_oi_change) else "CALL WRITING"
            if bias != previous_bias or not timeline:
                timeline.append({
                    "Time": pd.Timestamp(row.captured_at).strftime("%H:%M"), "Event": bias,
                    "PCR": round(_num(row.pcr_oi), 2), "Spot": round(_num(row.spot), 2),
                })
                previous_bias = bias
        if abs(spot_slope) > 0:
            timeline.append({"Time": pd.Timestamp(h.iloc[-1]["captured_at"]).strftime("%H:%M"), "Event": "PRICE MOMENTUM UP" if spot_slope > 0 else "PRICE MOMENTUM DOWN", "PCR": round(_num(h.iloc[-1]["pcr_oi"]), 2), "Spot": round(_num(h.iloc[-1]["spot"]), 2)})

        vote = "CE" if bullish_flow >= 60 else "PE" if bearish_flow >= 60 else "WAIT"
        state = "STRONG PUT WRITING" if bullish_flow >= 72 else "STRONG CALL WRITING" if bearish_flow >= 72 else "MIXED / DEVELOPING"
        reasons = [
            f"Put flow {put_flow:.0f}/100 vs call flow {call_flow:.0f}/100",
            f"OI acceleration favours {'puts' if put_accel > call_accel else 'calls'}",
            f"Spot momentum is {'positive' if spot_slope > 0 else 'negative' if spot_slope < 0 else 'flat'}",
        ]
        return EngineResult(self.name, chosen, vote, reasons, {
            "flow_state": state, "snapshot_count": n, "minimum_snapshots": 4,
            "call_flow_score": round(call_flow, 1), "put_flow_score": round(put_flow, 1),
            "bullish_flow": round(bullish_flow, 1), "bearish_flow": round(bearish_flow, 1),
            "net_bullish_flow": round(bullish_flow - bearish_flow, 1),
            "oi_momentum": round(put_change - call_change, 2), "oi_acceleration": round(put_accel - call_accel, 2),
            "delta_flow": round(delta_flow, 5), "gamma_flow": round(gamma_flow, 6),
            "iv_expansion": round(iv_slope, 3), "gamma_wall": gamma_wall,
            "timeline": timeline[-12:], "heatmap": heatmap,
        })

    @staticmethod
    def _adapt_input(
        market_data: DecisionContext | Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Normalize context histories and the legacy dictionary contract."""

        if isinstance(market_data, DecisionContext):
            return {
                "history": market_data.decision_history,
                "strike_history": market_data.strike_history,
                "recommendation": market_data.recommendation,
                "option_result": market_data.market_snapshot.option_result,
            }
        if not isinstance(market_data, Mapping):
            return {}
        return {
            "history": market_data.get("history"),
            "strike_history": market_data.get("strike_history"),
            "recommendation": market_data.get("recommendation") if isinstance(market_data.get("recommendation"), Mapping) else {},
            "option_result": market_data.get("option_result") if isinstance(market_data.get("option_result"), Mapping) else {},
        }


class InstitutionalConfidenceEngine(BaseEngine):
    """Weighted, explainable confidence score for institutional alignment."""

    name = "Institutional Confidence Engine"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        recommendation = market_data.get("recommendation", {})
        recommendation = recommendation if isinstance(recommendation, Mapping) else {}
        flow = market_data.get("flow_result")
        confirmation = market_data.get("confirmation_result")
        cycle = market_data.get("cycle_result")
        candle = market_data.get("candle_dna_result")
        pattern = market_data.get("pattern_result")
        decision = market_data.get("decision_matrix_result")
        side = str(recommendation.get("side", "WAIT"))
        components = recommendation.get("component_scores", {}) or {}

        values = {
            "OI Acceleration": _num(getattr(flow, "score", 0), 40),
            "Call/Put Writing": _num(getattr(flow, "metadata", {}).get("bullish_flow" if side == "CE" else "bearish_flow"), 50),
            "Delta Flow": _clip(50 + _num(getattr(flow, "metadata", {}).get("delta_flow")) * (900 if side == "CE" else -900)),
            "Gamma Flow": _clip(50 + _num(getattr(flow, "metadata", {}).get("gamma_flow")) * (12000 if side == "CE" else -12000)),
            "IV Expansion": _clip(50 + abs(_num(getattr(flow, "metadata", {}).get("iv_expansion"))) * 15),
            "Volume Expansion": _num(components.get("Volume"), 50),
            "VWAP / Trend": _num(components.get("Trend"), 50),
            "Pattern AI": _num(getattr(pattern, "score", 0), 50),
            "Candle DNA": _num(getattr(candle, "score", 0), 50),
            "Market Cycle": _num(getattr(cycle, "score", 0), 50),
            "Institutional Confirmation": _num(getattr(confirmation, "score", 0), 50),
            "Decision Matrix": _num(getattr(decision, "score", 0), 50),
        }
        weights = {
            "OI Acceleration": .16, "Call/Put Writing": .14, "Delta Flow": .08,
            "Gamma Flow": .07, "IV Expansion": .04, "Volume Expansion": .09,
            "VWAP / Trend": .09, "Pattern AI": .08, "Candle DNA": .05,
            "Market Cycle": .07, "Institutional Confirmation": .13, "Decision Matrix": .10,
        }
        rows = []
        total = 0.0
        for name, score in values.items():
            points = score * weights[name]
            total += points
            rows.append({"Signal": name, "Score": round(score, 1), "Weight %": round(weights[name] * 100, 1), "Points": round(points, 1), "Aligned": score >= 65})
        total = _clip(total)
        if getattr(flow, "metadata", {}).get("snapshot_count", 0) < 4:
            total = min(total, 69)
        vote = side if total >= 72 and side in {"CE", "PE"} else "WAIT"
        label = "VERY STRONG" if total >= 88 else "STRONG" if total >= 76 else "BUILDING" if total >= 62 else "WEAK"
        return EngineResult(self.name, total, vote, [f"{r['Signal']} {r['Score']:.0f}" for r in rows if r["Aligned"]][:6] or ["Institutional evidence remains mixed"], {
            "confidence": round(total, 1), "label": label, "contributions": rows,
            "aligned_count": sum(1 for r in rows if r["Aligned"]), "total_count": len(rows),
        })

    @staticmethod
    def _adapt_input(
        market_data: DecisionContext | Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Normalize context engine results and the legacy dictionary contract."""

        if isinstance(market_data, DecisionContext):
            results = market_data.engine_results
            return {
                "recommendation": market_data.recommendation,
                "flow_result": results.get("institutional_flow"),
                "confirmation_result": results.get("institutional_confirmation"),
                "cycle_result": market_data.cycle_result,
                "candle_dna_result": results.get("candle_dna"),
                "pattern_result": results.get("pattern_recognition"),
                "decision_matrix_result": results.get("institutional_decision_matrix"),
            }
        if not isinstance(market_data, Mapping):
            return {}
        normalized = dict(market_data)
        if not isinstance(normalized.get("recommendation"), Mapping):
            normalized["recommendation"] = {}
        return normalized


class SignalValidationEngine(BaseEngine):
    name = "Signal Validation Framework"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        recommendation = market_data.get("recommendation", {})
        flow = market_data.get("flow_result")
        ice = market_data.get("ice_result")
        confirmation = market_data.get("confirmation_result")
        false_breakout = market_data.get("false_breakout_result")
        stability = market_data.get("stability_result")
        side = str(recommendation.get("side", "WAIT"))
        checks = [
            ("Base recommendation", bool(recommendation.get("confirmed")), _num(recommendation.get("confidence"))),
            ("Institutional flow", getattr(flow, "vote", "WAIT") in {side, "WAIT"} and _num(getattr(flow, "score", 0)) >= 60, _num(getattr(flow, "score", 0))),
            ("ICE confidence", _num(getattr(ice, "score", 0)) >= 72, _num(getattr(ice, "score", 0))),
            ("Institutional confirmation", _num(getattr(confirmation, "score", 0)) >= 65, _num(getattr(confirmation, "score", 0))),
            ("Recommendation stability", _num(getattr(stability, "score", 0)) >= 65, _num(getattr(stability, "score", 0))),
            ("False-breakout safety", _num(getattr(false_breakout, "score", 0)) < 55, 100 - _num(getattr(false_breakout, "score", 0))),
        ]
        passed = sum(1 for _, ok, _ in checks if ok)
        hard_block = not checks[-1][1] or side not in {"CE", "PE"}
        validated = passed >= 5 and not hard_block
        score = _clip(np.mean([score for _, _, score in checks]))
        vote = side if validated else "WAIT"
        return EngineResult(self.name, score, vote, [f"{name}: {'PASS' if ok else 'WAIT'}" for name, ok, _ in checks], {
            "validated": validated, "passed": passed, "total": len(checks),
            "checks": [{"Control": n, "Score": round(s, 1), "Status": "PASS" if ok else "WAIT"} for n, ok, s in checks],
            "decision": f"BUY {side}" if validated else f"WAIT {side}" if side in {"CE", "PE"} else "WAIT",
        })


class EarlyWarningEngine(BaseEngine):
    name = "AI Early Warning Engine"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        recommendation = market_data.get("recommendation", {})
        flow = market_data.get("flow_result")
        ice = market_data.get("ice_result")
        validation = market_data.get("validation_result")
        side = str(recommendation.get("side", "WAIT"))
        confidence = _num(getattr(ice, "score", 0))
        flow_metadata = getattr(flow, "metadata", {})
        flow_metadata = flow_metadata if isinstance(flow_metadata, Mapping) else {}
        validation_metadata = getattr(validation, "metadata", {})
        validation_metadata = validation_metadata if isinstance(validation_metadata, Mapping) else {}
        acceleration = abs(_num(flow_metadata.get("oi_acceleration")))
        snapshots = int(_num(flow_metadata.get("snapshot_count")))
        if validation_metadata.get("validated"):
            state = "TRIGGER CONFIRMED"
            eta = "NOW"
            probability = max(confidence, 75)
        elif side in {"CE", "PE"} and confidence >= 60 and snapshots >= 4:
            state = f"EARLY {side} ALERT"
            eta_minutes = int(np.clip(9 - (confidence - 60) / 5 - min(acceleration, 3), 2, 8))
            eta = f"{eta_minutes}–{eta_minutes + 3} min"
            probability = _clip(confidence * .88)
        else:
            state = "NO EARLY SETUP"
            eta = "Not available"
            probability = min(confidence, 55)
        informational_only = state != "TRIGGER CONFIRMED"
        actionable = state != "NO EARLY SETUP" and bool(recommendation.get("confirmed"))
        return EngineResult(self.name, probability, side if actionable else "WAIT", [state], {
            "state": state, "probability": round(probability, 1), "estimated_trigger": eta,
            "side": side, "preparation": "Prepare contract and wait for validation" if "EARLY" in state else "No action",
            "informational_only": informational_only,
        })

    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(market_data, DecisionContext):
            return market_data if isinstance(market_data, Mapping) else {}
        results = market_data.engine_results if isinstance(market_data.engine_results, Mapping) else {}
        return {
            "recommendation": market_data.recommendation if isinstance(market_data.recommendation, Mapping) else {},
            "flow_result": market_data.flow_result or results.get("institutional_flow"),
            "ice_result": market_data.institutional_confidence_result or results.get("institutional_confidence"),
            "validation_result": market_data.validation_result or results.get("signal_validation"),
        }
