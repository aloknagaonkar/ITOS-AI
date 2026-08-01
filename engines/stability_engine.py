from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from .base_engine import BaseEngine, EngineResult
from itos_platform.decision_context import DecisionContext, MarketSnapshot


class RecommendationStabilityEngine(BaseEngine):
    name = "Recommendation Stability"

    def __init__(self, minimum_stability: float = 70.0) -> None:
        self.minimum_stability = float(minimum_stability)

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        """Analyze a typed context, adapting legacy dictionaries at the boundary."""
        context = self._adapt_input(market_data)
        recommendation = context.recommendation
        history = context.confidence_history
        phase_history = context.phase_history
        cycle = context.cycle_result

        side = str(recommendation.get("side", "WAIT"))
        current_conf = float(recommendation.get("confidence", 0.0))
        reasons: list[str] = []

        if not isinstance(history, pd.DataFrame) or history.empty:
            score = 45.0
            reasons.append("Stability is developing because fewer than two stored recommendations are available")
            sample_count = 0
            direction_changes = 0
            confidence_std = 0.0
            trend = "Developing"
        else:
            h = history.tail(10).copy()
            sides = h["side"].astype(str).tolist() if "side" in h else []
            sides.append(side)
            direction_changes = sum(1 for a, b in zip(sides, sides[1:]) if a != b)
            direction_consistency = (max(sides.count("CE"), sides.count("PE")) / max(len(sides), 1)) * 100

            confs = pd.to_numeric(h.get("calibrated_confidence", pd.Series(dtype=float)), errors="coerce").dropna().tolist()
            confs.append(current_conf)
            confidence_std = float(np.std(confs)) if len(confs) > 1 else 0.0
            confidence_consistency = float(np.clip(100 - confidence_std * 3.2, 0, 100))
            confidence_trend = confs[-1] - confs[0] if len(confs) > 1 else 0.0

            consensus_ratio = 50.0
            if "consensus_agreeing" in h and "consensus_total" in h:
                totals = pd.to_numeric(h["consensus_total"], errors="coerce").replace(0, np.nan)
                ratios = pd.to_numeric(h["consensus_agreeing"], errors="coerce") / totals * 100
                consensus_ratio = float(ratios.dropna().mean()) if not ratios.dropna().empty else 50.0

            phase_consistency = 70.0
            if isinstance(phase_history, pd.DataFrame) and not phase_history.empty and "phase" in phase_history:
                phases = phase_history.tail(8)["phase"].astype(str).tolist()
                phase_changes = sum(1 for a, b in zip(phases, phases[1:]) if a != b)
                phase_consistency = float(np.clip(100 - phase_changes * 18, 20, 100))

            manipulation = 0.0
            if cycle is not None:
                cycle_metadata = getattr(cycle, "metadata", {}) or {}
                manipulation = float(cycle_metadata.get("manipulation_score", 0.0))

            score = float(np.clip(
                direction_consistency * 0.35
                + confidence_consistency * 0.25
                + consensus_ratio * 0.20
                + phase_consistency * 0.20
                - direction_changes * 5
                - max(manipulation - 45, 0) * 0.35,
                0, 100,
            ))
            sample_count = len(h)
            if confidence_trend > 2:
                trend = "Building"
            elif confidence_trend < -2:
                trend = "Fading"
            else:
                trend = "Stable"
            reasons.extend([
                f"Direction changed {direction_changes} time(s) in the recent recommendation window",
                f"Confidence variability is {confidence_std:.1f} points",
                f"Recent consensus agreement averages {consensus_ratio:.0f}%",
            ])

        if score >= 85:
            label = "Highly Stable"
        elif score >= 70:
            label = "Stable"
        elif score >= 50:
            label = "Developing"
        elif score >= 30:
            label = "Unstable"
        else:
            label = "Highly Unstable"

        passed = score >= self.minimum_stability
        vote = side if passed else "WAIT"
        if not passed:
            reasons.append(f"Stability is below the {self.minimum_stability:.0f}% trigger threshold")

        return EngineResult(
            engine=self.name,
            score=score,
            vote=vote,
            explanation=reasons,
            metadata={
                "stability_score": score,
                "label": label,
                "trend": trend,
                "sample_count": sample_count,
                "direction_changes": direction_changes,
                "confidence_std": confidence_std,
                "minimum_required": self.minimum_stability,
                "passed": passed,
            },
        )

    @staticmethod
    def _adapt_input(
        market_data: DecisionContext | Mapping[str, Any],
    ) -> DecisionContext:
        """Normalize the legacy mapping without duplicating stability logic."""

        if isinstance(market_data, DecisionContext):
            return market_data

        snapshot = market_data.get("market_snapshot")
        if not isinstance(snapshot, MarketSnapshot):
            snapshot = MarketSnapshot.from_legacy(market_data)
        cycle_result = market_data.get("cycle_result")
        engine_results = dict(market_data.get("engine_results") or {})
        if cycle_result is not None:
            engine_results.setdefault("market_cycle", cycle_result)
        known = {
            "market_snapshot",
            "recommendation",
            "cycle_result",
            "engine_results",
            "confidence_history",
            "phase_history",
            "runtime",
            "runtime_configuration",
        }
        runtime_configuration = dict(market_data.get("runtime") or {})
        runtime_configuration.update(
            market_data.get("runtime_configuration") or {}
        )
        runtime_configuration.update(
            {key: value for key, value in market_data.items() if key not in known}
        )
        return DecisionContext(
            market_snapshot=snapshot,
            recommendation=market_data.get("recommendation") or {},
            engine_results=engine_results,
            confidence_history=market_data.get("confidence_history"),
            phase_history=market_data.get("phase_history"),
            runtime_configuration=runtime_configuration,
        )
