from __future__ import annotations

from typing import Any

import pandas as pd

from engines.explainable_ai import ExplainableAIEngine
from models.trade import AITradeOpportunity, ExecutionPlan, TradeCandidate


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_from_row(row: dict[str, Any], option_type: str) -> TradeCandidate:
    strike = _number(row.get("strike"))
    contract = str(row.get("contract") or f"{strike:.0f} {option_type}")
    return TradeCandidate(
        contract=contract,
        option_type=option_type,
        strike=strike,
        score=_number(row.get("final_score", row.get("score"))),
        confidence=_number(row.get("candidate_confidence", row.get("confidence"))),
        state=str(row.get("trade_state") or row.get("state") or "WATCH"),
        premium=_number(row.get("premium", row.get("ltp"))),
        entry_trigger=_number(row.get("entry_trigger")),
        stop_loss=_number(row.get("stop_loss")),
        target1=_number(row.get("target1")),
        target2=_number(row.get("target2")),
        delta=_number(row.get("delta", row.get("delta_abs"))),
        spread_pct=_number(row.get("spread_pct")),
        volume=_number(row.get("volume")),
        oi=_number(row.get("oi")),
    )


def _top_candidates(frame: Any, option_type: str) -> tuple[TradeCandidate, ...]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return ()
    return tuple(_candidate_from_row(row, option_type) for row in frame.head(5).to_dict("records"))


class AITradeEngine:
    """Orchestrates existing ITOS outputs without replacing their logic."""

    def __init__(self) -> None:
        self.explainer = ExplainableAIEngine()

    def build(
        self,
        recommendation: dict[str, Any],
        trade_plan_result: Any = None,
        decision_matrix_result: Any = None,
        regime_result: Any = None,
        flow_result: Any = None,
        confidence_history: Any = None,
    ) -> AITradeOpportunity:
        best = recommendation.get("best") or {}
        contract = str(best.get("contract") or "No qualified contract")
        option_type = str(recommendation.get("side") or "WAIT")

        plan_meta = getattr(trade_plan_result, "metadata", {}) or {}
        plan = plan_meta.get("plan") or {}
        action = "BUY" if recommendation.get("confirmed") else "WAIT"
        plan_state = str(plan.get("state") or recommendation.get("status") or "WAITING")
        if plan_state.upper() == "TRIGGERED":
            action = "BUY"

        entry_low = _number(plan.get("entry_low"), _number(best.get("entry_trigger")))
        entry_high = _number(plan.get("entry_high"), entry_low)
        targets = tuple(
            value for value in (
                _number(plan.get("target1"), _number(best.get("target1"))),
                _number(plan.get("target2"), _number(best.get("target2"))),
                _number(plan.get("target3")),
            ) if value > 0
        )
        stop_loss = _number(plan.get("stop_loss"), _number(best.get("stop_loss")))
        risk = max(entry_low - stop_loss, 0)
        reward = max((targets[1] if len(targets) > 1 else (targets[0] if targets else entry_low)) - entry_low, 0)
        risk_reward = reward / risk if risk > 0 else 0.0

        matrix_meta = getattr(decision_matrix_result, "metadata", {}) or {}
        regime_meta = getattr(regime_result, "metadata", {}) or {}
        flow_meta = getattr(flow_result, "metadata", {}) or {}

        confidence = _number(recommendation.get("confidence"))
        early_move = recommendation.get("early_move") or {}
        best_score = _number(best.get("score"), _number(recommendation.get("model_probability")))
        institutional_score = _number(matrix_meta.get("overall_score"), _number(flow_meta.get("score")))
        ai_score = min(100.0, max(0.0, 0.45 * best_score + 0.35 * confidence + 0.20 * institutional_score))


        # Compare the latest confidence snapshot with the closest snapshot at
        # least five minutes earlier. This provides a concise change narrative
        # without inventing unsupported OI or premium movements.
        recent_changes: list[dict[str, Any]] = []
        change_summary = "Waiting for enough history to compare the last 5 minutes."
        if isinstance(confidence_history, pd.DataFrame) and not confidence_history.empty:
            history = confidence_history.copy()
            if "captured_at" in history.columns:
                history["captured_at"] = pd.to_datetime(history["captured_at"], errors="coerce")
                history = history.dropna(subset=["captured_at"]).sort_values("captured_at")
            if len(history) >= 2:
                latest = history.iloc[-1]
                cutoff = latest["captured_at"] - pd.Timedelta(minutes=5)
                earlier_rows = history[history["captured_at"] <= cutoff]
                earlier = earlier_rows.iloc[-1] if not earlier_rows.empty else history.iloc[0]
                metrics = [
                    ("Market confidence", "market_confidence"),
                    ("Directional confidence", "direction_confidence"),
                    ("Trigger confidence", "trigger_confidence"),
                    ("AI confidence", "calibrated_confidence"),
                ]
                positive = 0
                negative = 0
                for label, column in metrics:
                    if column not in history.columns:
                        continue
                    before = _number(earlier.get(column))
                    now = _number(latest.get(column))
                    delta = now - before
                    if abs(delta) < 0.5:
                        state = "Stable"
                    elif delta > 0:
                        state = "Improving"
                        positive += 1
                    else:
                        state = "Weakening"
                        negative += 1
                    recent_changes.append({"label": label, "before": before, "now": now, "delta": delta, "state": state})
                old_side = str(earlier.get("side") or "WAIT")
                new_side = str(latest.get("side") or "WAIT")
                if old_side != new_side:
                    recent_changes.append({"label": "Preferred side", "before_text": old_side, "now_text": new_side, "state": "Rotated"})
                if positive > negative:
                    change_summary = f"Momentum is strengthening: {positive} confidence measures improved."
                elif negative > positive:
                    change_summary = f"Momentum is weakening: {negative} confidence measures declined."
                else:
                    change_summary = "Confidence is broadly stable; wait for a clearer expansion."

        missing_conditions = list(recommendation.get("missing_conditions", []) or [])
        watch_next = missing_conditions[:5]
        if not watch_next:
            if action == "BUY":
                watch_next = ["Hold the entry trigger", "Maintain volume and directional confirmation", "Avoid a new hard blocker"]
            else:
                watch_next = ["Directional confidence above threshold", "Trade readiness confirmation", "Clear CE/PE strength advantage"]

        return AITradeOpportunity(
            contract=contract,
            option_type=option_type,
            recommendation=action,
            ai_score=ai_score,
            confidence=confidence,
            directional_confidence=_number(recommendation.get("directional_confidence")),
            trade_readiness=_number(recommendation.get("trade_readiness")),
            ce_strength=_number(recommendation.get("ce_strength")),
            pe_strength=_number(recommendation.get("pe_strength")),
            strength_advantage=_number(recommendation.get("strength_advantage")),
            recommended_side=str(recommendation.get("recommended_side") or "WAIT"),
            early_move_side=str(early_move.get("side") or "WAIT"),
            early_move_probability=_number(early_move.get("probability")),
            early_move_state=str(early_move.get("state") or "NO EARLY EDGE"),
            institutional_score=institutional_score,
            institutional_bias=str(flow_meta.get("direction") or flow_meta.get("bias") or recommendation.get("direction") or "NEUTRAL"),
            market_regime=str(regime_meta.get("regime") or recommendation.get("regime", {}).get("name") or "UNKNOWN"),
            trade_quality=_number(recommendation.get("trade_quality")),
            execution=ExecutionPlan(
                action=action,
                entry_low=entry_low,
                entry_high=entry_high,
                stop_loss=stop_loss,
                targets=targets,
                risk_reward=risk_reward,
                state=plan_state,
                lots=int(_number(plan.get("lots"))),
                quantity=int(_number(plan.get("quantity"))),
            ),
            reasons=self.explainer.explain(recommendation),
            blockers=self.explainer.blockers(recommendation),
            top_ce=_top_candidates(recommendation.get("ce_top5"), "CE"),
            top_pe=_top_candidates(recommendation.get("pe_top5"), "PE"),
            metadata={
                "status": recommendation.get("status", "WAIT"),
                "condition_checklist": recommendation.get("condition_checklist", []),
                "missing_conditions": recommendation.get("missing_conditions", []),
                "passed_conditions": recommendation.get("passed_conditions", 0),
                "total_conditions": recommendation.get("total_conditions", 0),
                "direction": recommendation.get("direction", "NEUTRAL"),
                "recent_changes": recent_changes,
                "change_summary": change_summary,
                "watch_next": watch_next,
            },
        )
