from __future__ import annotations

from typing import Any, Iterable


def _clean(items: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in output:
            output.append(text)
    return output


class ExplainableAIEngine:
    """Converts existing engine output into concise, trader-readable evidence."""

    def explain(self, recommendation: dict[str, Any], max_reasons: int = 7) -> tuple[str, ...]:
        reasons = list(recommendation.get("reasons") or [])
        components = recommendation.get("component_scores") or {}

        for name, value in components.items():
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if score >= 70:
                reasons.append(f"{name} confirmation is strong ({score:.0f}/100)")

        confidence = float(recommendation.get("confidence") or 0)
        if confidence >= 75:
            reasons.append(f"Calibrated confidence supports the setup ({confidence:.0f}%)")

        best = recommendation.get("best") or {}
        if best:
            spread = float(best.get("spread_pct") or 0)
            delta = abs(float(best.get("delta") or best.get("delta_abs") or 0))
            if 0 < spread <= 2.0:
                reasons.append(f"Bid-ask spread is execution-friendly ({spread:.2f}%)")
            if 0.35 <= delta <= 0.75:
                reasons.append(f"Delta is in the preferred directional range ({delta:.2f})")

        cleaned = _clean(reasons)
        return tuple(cleaned[:max_reasons])

    def blockers(self, recommendation: dict[str, Any], max_items: int = 5) -> tuple[str, ...]:
        items = list(recommendation.get("blockers") or [])
        items.extend(recommendation.get("missing_conditions") or [])
        return tuple(_clean(items)[:max_items])
