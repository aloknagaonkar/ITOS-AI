from __future__ import annotations

from datetime import datetime
from typing import Any

from .base_engine import BaseEngine, EngineResult


class DataHealthEngine(BaseEngine):
    """Validates whether the current decision inputs are complete and fresh enough."""

    name = "Data Health Engine"

    def __init__(self, recommendation: dict[str, Any] | None = None) -> None:
        # Decision state is injected separately so it never contaminates MarketSnapshot.
        self.recommendation = recommendation

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        flags: list[str] = []
        explanations: list[str] = []
        score = 100.0

        option_result = market_data.get("option_result") or {}
        intelligence = market_data.get("intelligence") or {}
        recommendation = self.recommendation if self.recommendation is not None else market_data.get("recommendation") or {}
        last_refresh = str(market_data.get("last_refresh") or "").strip()

        chain = option_result.get("chain")
        chain_rows = len(chain) if hasattr(chain, "__len__") else 0
        if chain_rows <= 0:
            score -= 45
            flags.append("OPTION_CHAIN_MISSING")
            explanations.append("Option-chain rows are unavailable.")
        elif chain_rows < 6:
            score -= 15
            flags.append("OPTION_CHAIN_THIN")
            explanations.append(f"Only {chain_rows} option-chain rows are available.")
        else:
            explanations.append(f"Option chain contains {chain_rows} rows.")

        required_intelligence = ("state", "spot", "atm", "support", "resistance")
        missing = [key for key in required_intelligence if intelligence.get(key) is None]
        if missing:
            score -= min(30, len(missing) * 6)
            flags.append("INTELLIGENCE_FIELDS_MISSING")
            explanations.append("Missing intelligence fields: " + ", ".join(missing))
        else:
            explanations.append("Core market-state fields are present.")

        if not recommendation:
            score -= 20
            flags.append("RECOMMENDATION_MISSING")
            explanations.append("Decision recommendation has not been produced.")
        else:
            explanations.append("Recommendation package is available.")

        age_seconds: float | None = None
        if last_refresh:
            try:
                now = datetime.now().astimezone()
                parsed = datetime.strptime(last_refresh, "%H:%M:%S").replace(
                    year=now.year, month=now.month, day=now.day, tzinfo=now.tzinfo
                )
                age_seconds = max(0.0, (now - parsed).total_seconds())
                if age_seconds > 180:
                    score -= 35
                    flags.append("DATA_STALE")
                    explanations.append(f"Last refresh is {age_seconds:.0f} seconds old.")
                elif age_seconds > 90:
                    score -= 15
                    flags.append("DATA_AGING")
                    explanations.append(f"Last refresh is {age_seconds:.0f} seconds old.")
                else:
                    explanations.append(f"Data refreshed {age_seconds:.0f} seconds ago.")
            except ValueError:
                score -= 10
                flags.append("REFRESH_TIME_INVALID")
                explanations.append("Refresh timestamp could not be validated.")
        else:
            score -= 25
            flags.append("REFRESH_TIME_MISSING")
            explanations.append("No refresh timestamp is available.")

        score = max(0.0, min(100.0, score))
        if score >= 85:
            status, vote = "HEALTHY", "PASS"
        elif score >= 65:
            status, vote = "DEGRADED", "CAUTION"
        elif score >= 40:
            status, vote = "STALE / INCOMPLETE", "BLOCK"
        else:
            status, vote = "TRADING DISABLED", "BLOCK"

        return EngineResult(
            engine=self.name,
            score=score,
            vote=vote,
            explanation=explanations,
            metadata={
                "status": status,
                "flags": flags,
                "chain_rows": chain_rows,
                "age_seconds": age_seconds,
                "trading_allowed": vote != "BLOCK",
            },
        )
