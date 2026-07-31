from __future__ import annotations

from typing import Any, Iterable

from .base_engine import BaseEngine, EngineResult
from .institutional_confidence import InstitutionalConfidenceEngine
from .strike_ranker import StrikeRanker


def _normalise_vote(value: Any) -> str:
    text = str(value or "WAIT").upper()
    if "CE" in text or text in {"BUY", "BULLISH"}:
        return "CE"
    if "PE" in text or text in {"SELL", "BEARISH"}:
        return "PE"
    return "WAIT"


class AIOrchestrator:
    """Runs enabled engines and produces one explainable dashboard payload."""

    def __init__(
        self,
        engines: Iterable[BaseEngine] | None = None,
        engine_weights: dict[str, float] | None = None,
        strike_ranker: StrikeRanker | None = None,
    ) -> None:
        self.engines = list(engines or [InstitutionalConfidenceEngine()])
        self.engine_weights = dict(engine_weights or {})
        self.strike_ranker = strike_ranker or StrikeRanker()

    def evaluate(self, market_data: dict[str, Any]) -> dict[str, Any]:
        results: list[EngineResult] = []
        errors: list[str] = []
        totals = {"CE": 0.0, "PE": 0.0, "WAIT": 0.0}
        total_weight = 0.0

        for engine in self.engines:
            try:
                result = engine.analyze(market_data)
                results.append(result)
                weight = self.engine_weights.get(result.engine, result.weight)
                effective = max(float(weight), 0.0)
                confidence = float(result.confidence or result.score) / 100.0
                totals[_normalise_vote(result.vote)] += effective * confidence
                total_weight += effective
            except Exception as exc:  # isolate one engine from the complete dashboard
                errors.append(f"{engine.name}: {exc}")

        denominator = sum(totals.values()) or 1.0
        shares = {key: value / denominator * 100.0 for key, value in totals.items()}
        leading_side = max(("CE", "PE"), key=lambda side: shares[side])
        directional_gap = abs(shares["CE"] - shares["PE"])
        wait_share = shares["WAIT"]
        conflict_score = max(0.0, min(100.0, 100.0 - directional_gap + wait_share * 0.25))
        confidence = max(0.0, min(100.0, shares[leading_side] - conflict_score * 0.20))
        decision = leading_side if confidence >= 58.0 and shares[leading_side] >= 52.0 else "WAIT"

        reasons: list[str] = []
        blockers: list[str] = []
        for result in sorted(results, key=lambda item: float(item.confidence or item.score), reverse=True):
            target = reasons if _normalise_vote(result.vote) == decision and decision != "WAIT" else blockers
            for line in result.explanation:
                if line not in target:
                    target.append(line)

        strikes = market_data.get("strikes") or market_data.get("option_chain") or []
        spot = market_data.get("spot") or market_data.get("spot_price") or market_data.get("underlying_price")
        ranked_strikes = self.strike_ranker.rank(strikes, side=decision, spot=spot, limit=5) if decision in {"CE", "PE"} and isinstance(strikes, list) else []
        best = ranked_strikes[0] if ranked_strikes else None

        grade = "A+" if confidence >= 88 and conflict_score < 30 else "A" if confidence >= 78 else "B" if confidence >= 68 else "C" if decision != "WAIT" else "AVOID"
        status = "ACTIONABLE" if decision != "WAIT" and best else "DIRECTIONAL" if decision != "WAIT" else "WAITING"

        return {
            "decision": f"BUY {decision}" if decision in {"CE", "PE"} else "WAIT",
            "side": decision,
            "confidence": round(confidence, 1),
            "grade": grade,
            "status": status,
            "vote_shares": {key: round(value, 1) for key, value in shares.items()},
            "conflict_score": round(conflict_score, 1),
            "reasons": reasons[:8],
            "blockers": blockers[:6],
            "ranked_strikes": ranked_strikes,
            "best": best,
            "engine_results": [result.to_dict() for result in results],
            "engine_errors": errors,
            "available_engine_weight": round(total_weight, 3),
        }
