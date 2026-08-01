from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from .base_engine import BaseEngine, EngineResult


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


def _session_features(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty or "captured_at" not in history:
        return pd.DataFrame()
    frame = history.copy()
    frame["captured_at"] = pd.to_datetime(frame["captured_at"], errors="coerce")
    frame = frame.dropna(subset=["captured_at"]).sort_values("captured_at")
    if frame.empty:
        return pd.DataFrame()
    frame["session_date"] = frame["captured_at"].dt.date.astype(str)
    rows: list[dict[str, Any]] = []
    for session_date, group in frame.groupby("session_date"):
        group = group.sort_values("captured_at")
        first, last = group.iloc[0], group.iloc[-1]
        spot_open = _num(first.get("spot"))
        spot_close = _num(last.get("spot"), spot_open)
        move = spot_close - spot_open
        rows.append({
            "session_date": session_date,
            "samples": len(group),
            "spot_open": spot_open,
            "spot_close": spot_close,
            "move_points": move,
            "move_pct": (move / spot_open * 100.0) if spot_open else 0.0,
            "pcr_oi": _num(group.get("pcr_oi", pd.Series([0])).mean()),
            "pcr_volume": _num(group.get("pcr_volume", pd.Series([0])).mean()),
            "atm_iv": _num(group.get("atm_iv", pd.Series([0])).mean()),
            "iv_skew": _num(group.get("iv_skew", pd.Series([0])).mean()),
            "combined_score": _num(group.get("combined_score", pd.Series([0])).mean()),
            "confidence": _num(group.get("confidence", pd.Series([0])).mean()),
            "oi_imbalance": _num((group.get("put_oi", pd.Series([0])) - group.get("call_oi", pd.Series([0]))).mean()),
            "volume_imbalance": _num((group.get("put_volume", pd.Series([0])) - group.get("call_volume", pd.Series([0]))).mean()),
            "state": str(last.get("state", "Unknown")),
        })
    return pd.DataFrame(rows).sort_values("session_date", ascending=False).reset_index(drop=True)


class HistoricalSimilarityEngine(BaseEngine):
    name = "Historical Similarity Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        history = market_data.get("history")
        current = market_data.get("current", {}) or {}
        sessions = _session_features(history)
        if sessions.empty or len(sessions) < 2:
            return EngineResult(self.name, 0.0, "WAIT", ["At least two stored trading sessions are required."], {
                "status": "WARMING UP", "matches": [], "sessions_scanned": len(sessions),
            })

        current_date = datetime.now().astimezone().date().isoformat()
        candidates = sessions[sessions["session_date"] != current_date].copy()
        if candidates.empty:
            return EngineResult(self.name, 0.0, "WAIT", ["No completed prior session is available yet."], {
                "status": "WARMING UP", "matches": [], "sessions_scanned": len(sessions),
            })

        target = {
            "pcr_oi": _num(current.get("pcr_oi")),
            "pcr_volume": _num(current.get("pcr_volume")),
            "atm_iv": _num(current.get("atm_iv")),
            "iv_skew": _num(current.get("iv_skew")),
            "combined_score": _num(current.get("combined_score")),
            "confidence": _num(current.get("confidence")),
            "oi_imbalance": _num(current.get("oi_imbalance")),
            "volume_imbalance": _num(current.get("volume_imbalance")),
        }
        scales = {
            "pcr_oi": 0.45, "pcr_volume": 0.55, "atm_iv": 8.0, "iv_skew": 8.0,
            "combined_score": 30.0, "confidence": 30.0,
            "oi_imbalance": max(abs(target["oi_imbalance"]), 1.0),
            "volume_imbalance": max(abs(target["volume_imbalance"]), 1.0),
        }
        weights = {"pcr_oi": .16, "pcr_volume": .10, "atm_iv": .11, "iv_skew": .09,
                   "combined_score": .20, "confidence": .16, "oi_imbalance": .11, "volume_imbalance": .07}
        similarities = []
        for _, row in candidates.iterrows():
            distance = 0.0
            for key, weight in weights.items():
                distance += min(abs(_num(row.get(key)) - target[key]) / scales[key], 2.0) * weight
            similarity = _clip(100.0 * (1.0 - min(distance, 1.0)))
            direction = "CE" if _num(row.get("move_points")) > 0 else "PE" if _num(row.get("move_points")) < 0 else "WAIT"
            similarities.append({
                "Date": row["session_date"], "Similarity %": round(similarity, 1),
                "Outcome": direction, "Move Points": round(_num(row.get("move_points")), 1),
                "Move %": round(_num(row.get("move_pct")), 2), "Samples": int(row.get("samples", 0)),
                "State": row.get("state", "Unknown"),
            })
        matches = sorted(similarities, key=lambda item: item["Similarity %"], reverse=True)[:5]
        top = matches[0]
        strong = [m for m in matches if m["Similarity %"] >= 70]
        ce = sum(m["Similarity %"] for m in strong if m["Outcome"] == "CE")
        pe = sum(m["Similarity %"] for m in strong if m["Outcome"] == "PE")
        vote = "CE" if ce > pe * 1.15 else "PE" if pe > ce * 1.15 else "WAIT"
        score = _num(top["Similarity %"])
        return EngineResult(self.name, score, vote, [
            f"Scanned {len(candidates)} completed sessions.",
            f"Top historical match is {top['Date']} at {top['Similarity %']:.1f}% similarity.",
            f"The top match moved {top['Move Points']:+.1f} points.",
        ], {"status": "READY", "matches": matches, "sessions_scanned": len(candidates), "top_match": top,
            "historical_vote": vote, "strong_matches": len(strong)})


class InstitutionalPlaybookEngine(BaseEngine):
    name = "Institutional Playbook Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        regime = market_data.get("regime_result")
        flow = market_data.get("flow_result")
        energy = market_data.get("energy_result")
        pattern = market_data.get("pattern_result")
        intelligence = market_data.get("intelligence", {}) or {}
        price = intelligence.get("price", {}) or {}
        summary = (market_data.get("option_result", {}) or {}).get("summary", {}) or {}
        flow_meta = getattr(flow, "metadata", {}) or {}
        regime_name = str(getattr(regime, "metadata", {}).get("regime", "Unknown"))
        energy_score = _num(getattr(energy, "score", 0))
        net_flow = _num(flow_meta.get("net_bullish_flow"))
        oi_accel = _num(flow_meta.get("oi_acceleration"))
        spot = _num(summary.get("spot"))
        vwap = _num(price.get("vwap"), spot)
        atr = max(_num(price.get("atr"), 1.0), 1e-9)
        vwap_dist = (spot - vwap) / atr
        primary_pattern = str(getattr(pattern, "metadata", {}).get("primary_pattern", {}).get("name", "None"))

        candidates = [
            ("Trend Day Continuation", 35 + (25 if regime_name == "Trend Day" else 0) + energy_score * .25 + abs(vwap_dist) * 12,
             "CE" if vwap_dist > 0 else "PE" if vwap_dist < 0 else "WAIT"),
            ("VWAP Reclaim", 25 + max(vwap_dist, 0) * 30 + max(net_flow, 0) * .35, "CE"),
            ("VWAP Rejection", 25 + max(-vwap_dist, 0) * 30 + max(-net_flow, 0) * .35, "PE"),
            ("Put Writing Expansion", 30 + max(net_flow, 0) * .45 + max(oi_accel, 0) * 5, "CE"),
            ("Call Writing Breakdown", 30 + max(-net_flow, 0) * .45 + max(-oi_accel, 0) * 5, "PE"),
            ("Volatility Expansion", 25 + (25 if regime_name in {"Breakout Day", "Volatility Expansion"} else 0) + energy_score * .35, "CE" if net_flow > 0 else "PE" if net_flow < 0 else "WAIT"),
            ("Range Compression", 35 + (40 if regime_name == "Range Day" else 0) + max(0, 60-energy_score) * .3, "WAIT"),
            ("Pattern-Led Breakout", 25 + (30 if primary_pattern != "None" else 0) + energy_score * .25, getattr(pattern, "vote", "WAIT")),
        ]
        ranked = sorted([{"Playbook": n, "Score": round(_clip(s), 1), "Vote": v} for n, s, v in candidates], key=lambda x: x["Score"], reverse=True)
        primary = ranked[0]
        confidence = primary["Score"]
        status = "ACTIVE" if confidence >= 75 else "DEVELOPING" if confidence >= 55 else "INACTIVE"
        vote = primary["Vote"] if confidence >= 65 else "WAIT"
        return EngineResult(self.name, confidence, vote, [
            f"Primary playbook: {primary['Playbook']}.", f"Market regime: {regime_name}.",
            f"Market energy: {energy_score:.1f}; net flow: {net_flow:+.1f}.",
        ], {"primary": primary, "status": status, "rankings": ranked, "pattern": primary_pattern})


class MarketReplayEngine(BaseEngine):
    name = "Market Replay Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        history = market_data.get("history")
        if history is None or history.empty:
            return EngineResult(self.name, 0.0, "WAIT", ["No stored snapshots are available for replay."], {"events": [], "status": "WARMING UP"})
        frame = history.copy().sort_values("captured_at")
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], errors="coerce")
        frame = frame.dropna(subset=["captured_at"])
        events: list[dict[str, Any]] = []
        previous_state = None
        previous_conf = None
        previous_spot = None
        for _, row in frame.tail(120).iterrows():
            state = str(row.get("state", "Unknown"))
            confidence = _num(row.get("confidence"))
            spot = _num(row.get("spot"))
            event = None
            reason = None
            if previous_state is None:
                event, reason = "Session Tracking Started", f"Initial state {state}"
            elif state != previous_state:
                event, reason = "Market State Changed", f"{previous_state} → {state}"
            elif previous_conf is not None and abs(confidence - previous_conf) >= 8:
                event, reason = "Confidence Shift", f"{previous_conf:.0f}% → {confidence:.0f}%"
            elif previous_spot is not None and abs(spot - previous_spot) >= max(abs(previous_spot) * .0015, 20):
                event, reason = "Price Impulse", f"Spot moved {spot-previous_spot:+.1f} points"
            if event:
                events.append({"Time": row["captured_at"].strftime("%H:%M:%S"), "Event": event,
                               "Narrative": reason, "Spot": round(spot, 2), "Confidence": round(confidence, 1), "State": state})
            previous_state, previous_conf, previous_spot = state, confidence, spot
        events = events[-30:]
        score = _clip(len(events) * 4)
        return EngineResult(self.name, score, "WAIT", [f"Generated {len(events)} material replay events."], {"events": events, "status": "READY" if events else "QUIET"})


class ExplainableSessionReportEngine(BaseEngine):
    name = "Explainable AI Session Report"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        regime = market_data.get("regime_result")
        smi = market_data.get("smi_result")
        energy = market_data.get("energy_result")
        similarity = market_data.get("similarity_result")
        playbook = market_data.get("playbook_result")
        recommendation = market_data.get("recommendation", {}) or {}
        regime_name = getattr(regime, "metadata", {}).get("regime", "Unknown")
        smi_score = _num(getattr(smi, "score", 0))
        energy_score = _num(getattr(energy, "score", 0))
        play = getattr(playbook, "metadata", {}).get("primary", {})
        top_match = getattr(similarity, "metadata", {}).get("top_match", {})
        side = recommendation.get("side", "WAIT")
        confirmed = bool(recommendation.get("confirmed"))
        decision_text = f"a confirmed {side} setup" if confirmed else f"a {side} watch setup" if side in {"CE", "PE"} else "no trade"
        report = (
            f"The current market is classified as {regime_name}. Smart Money Index is {smi_score:.0f}/100 "
            f"and market energy is {energy_score:.0f}/100. The leading institutional playbook is "
            f"{play.get('Playbook', 'still developing')} with {play.get('Score', 0):.0f}% confidence. "
            f"The decision engine currently indicates {decision_text}."
        )
        if top_match:
            report += (f" The closest stored historical session is {top_match.get('Date')} at "
                       f"{top_match.get('Similarity %', 0):.0f}% similarity; that session moved "
                       f"{top_match.get('Move Points', 0):+.1f} points.")
        report += " Historical similarity is supporting evidence only and cannot override live validation or risk controls."
        score = _clip(np.mean([smi_score, energy_score, _num(getattr(similarity, "score", 0)), _num(getattr(playbook, "score", 0))]))
        return EngineResult(self.name, score, side if confirmed else "WAIT", [report], {"report": report, "grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"})
