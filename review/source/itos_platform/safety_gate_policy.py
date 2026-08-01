"""Monotonic enforcement of the dashboard's existing decision safety gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping


@dataclass(frozen=True)
class SafetyDecision:
    """Typed outcome of applying the existing recommendation vetoes."""

    trade_allowed: bool
    final_state: str
    blockers: tuple[str, ...]
    reasons: tuple[str, ...]


class SafetyGatePolicy:
    """Consolidate legacy vetoes without changing their thresholds or ordering."""

    def enforce(
        self,
        recommendation: MutableMapping[str, Any],
        *,
        cycle_result: Any = None,
        stability_result: Any = None,
        false_breakout_result: Any = None,
        confirmation_result: Any = None,
        validation_result: Any = None,
        data_health_result: Any = None,
    ) -> SafetyDecision:
        if not isinstance(recommendation, MutableMapping):
            return SafetyDecision(False, "WAIT", ("Malformed recommendation",), ("Critical recommendation input is malformed.",))

        reasons: list[str] = []
        blockers = list(recommendation.get("blockers", []) or [])
        side = str(recommendation.get("side") or "WAIT")
        if "side" not in recommendation or "confirmed" not in recommendation:
            recommendation.update(side="WAIT", confirmed=False, status="WAIT — RECOMMENDATION UNAVAILABLE")
            blockers.append("Critical recommendation input is malformed")

        def block(status: str, reason: str) -> None:
            recommendation["confirmed"] = False
            recommendation["status"] = status
            blockers.append(reason)
            reasons.append(reason)

        if recommendation.get("confirmed") and cycle_result is not None:
            meta = getattr(cycle_result, "metadata", {}) or {}
            gate = bool(meta.get("trade_allowed", False)) and getattr(cycle_result, "vote", None) in {side, "WAIT"}
            if not gate:
                block(f"WATCH {side} — MARKET CYCLE NOT READY", f"Market phase is {meta.get('phase', 'Unknown')}; directional expansion is required")
        if recommendation.get("confirmed") and stability_result is not None:
            meta = getattr(stability_result, "metadata", {}) or {}
            if not bool(meta.get("passed", False)):
                block(f"WATCH {side} — STABILITY DEVELOPING", f"Recommendation stability is {meta.get('stability_score', 0):.0f}%, below the 70% trigger threshold")
        if recommendation.get("confirmed") and false_breakout_result is not None:
            if (getattr(false_breakout_result, "metadata", {}) or {}).get("blocked"):
                block(f"WAIT {side} — FALSE BREAKOUT RISK", f"False-breakout risk is {getattr(false_breakout_result, 'score', 0):.0f}/100")
        if recommendation.get("confirmed") and confirmation_result is not None:
            meta = getattr(confirmation_result, "metadata", {}) or {}
            if meta.get("status") != "CONFIRMED":
                block(f"WATCH {side} — INSTITUTIONAL CONFIRMATION {meta.get('status', 'DEVELOPING')}", f"Institutional confirmation is {getattr(confirmation_result, 'score', 0):.0f}/100")
        if recommendation.get("confirmed") and validation_result is not None:
            meta = getattr(validation_result, "metadata", {}) or {}
            if not meta.get("validated", False):
                block(f"WATCH {side} — FLOW VALIDATION DEVELOPING", f"Version 7.7 validation passed {meta.get('passed', 0)} of {meta.get('total', 6)} controls")
        if recommendation.get("confirmed") and data_health_result is not None:
            meta = getattr(data_health_result, "metadata", {}) or {}
            if not meta.get("trading_allowed", True):
                block(f"WAIT {side} — DATA HEALTH UNAVAILABLE", "Critical market data is unhealthy")

        recommendation["blockers"] = list(dict.fromkeys(blockers))
        allowed = bool(recommendation.get("confirmed", False))
        return SafetyDecision(allowed, "BUY" if allowed else "WAIT", tuple(recommendation["blockers"]), tuple(reasons))
