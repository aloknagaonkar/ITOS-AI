from __future__ import annotations

from typing import Any
import math
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


class InstitutionalDecisionMatrixEngine(BaseEngine):
    """Build one explainable institutional decision matrix from existing engines."""

    name = "Institutional Decision Matrix"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        recommendation = market_data.get("recommendation", {})
        intelligence = market_data.get("intelligence", {})
        cycle = market_data.get("cycle_result")
        footprint = market_data.get("footprint_result")
        confirmation = market_data.get("confirmation_result")
        candle = market_data.get("candle_dna_result")
        pattern = market_data.get("pattern_result")
        false_breakout = market_data.get("false_breakout_result")

        side = str(recommendation.get("side", "WAIT"))
        components = recommendation.get("component_scores", {}) or {}
        trend = _num(components.get("Trend"), 50)
        oi = _num(components.get("OI / Institutional Flow"), 50)
        volume = _num(components.get("Volume"), 50)
        greeks = _num(components.get("Greeks"), 50)
        liquidity = _num(components.get("Liquidity"), 50)
        risk_reward = _num(components.get("Risk / Reward"), 50)
        pattern_score = _num(getattr(pattern, "score", 0), 50)
        phase_score = _num(getattr(cycle, "score", 0), 50)
        footprint_score = _num(getattr(footprint, "score", 0), 50)
        candle_score = _num(getattr(candle, "score", 0), 50)
        confirmation_score = _num(getattr(confirmation, "score", 0), 50)
        false_breakout_score = _num(getattr(false_breakout, "score", 0), 0)
        safety_score = 100 - false_breakout_score

        rows = [
            ("Trend", trend, "Price trend, EMA and VWAP alignment"),
            ("OI / Flow", oi, "Option-chain positioning and stored flow"),
            ("Volume", volume, "Underlying participation"),
            ("Greeks", greeks, "Delta, gamma and responsiveness"),
            ("Liquidity", liquidity, "Spread, OI and traded volume"),
            ("Pattern", pattern_score, "Institutional pattern recognition"),
            ("Candle DNA", candle_score, "Current candle quality"),
            ("Market Phase", phase_score, "Cycle and expansion readiness"),
            ("Institutional Activity", footprint_score, "Footprint strength"),
            ("Confirmation", confirmation_score, "Cross-engine agreement"),
            ("Breakout Safety", safety_score, "Protection against false breakouts"),
            ("Risk / Reward", risk_reward, "Contract risk quality"),
        ]
        weights = [1.15, 1.25, 1.0, 1.0, .8, .9, .75, 1.0, 1.15, 1.25, 1.2, .8]
        overall = float(np.average([r[1] for r in rows], weights=weights))
        trade_quality = _clip(overall * .65 + _num(recommendation.get("confidence"), 50) * .35)
        if recommendation.get("confirmed") and confirmation_score >= 70 and safety_score >= 55:
            status = f"BUY {side}"
        elif recommendation.get("status") == "NO TRADE" or safety_score < 45:
            status = "NO TRADE"
        else:
            status = f"WAIT {side}" if side in {"CE", "PE"} else "WAIT"

        matrix = []
        for category, score, evidence in rows:
            label = "Strong" if score >= 80 else "Positive" if score >= 65 else "Neutral" if score >= 45 else "Weak" if score >= 30 else "Risk"
            matrix.append({"Category": category, "Score": round(score, 1), "Status": label, "Evidence": evidence})

        grade = "A+" if trade_quality >= 90 else "A" if trade_quality >= 82 else "B" if trade_quality >= 70 else "C" if trade_quality >= 55 else "D"
        reasons = [f"{row['Category']} {row['Score']:.0f}" for row in matrix if row["Score"] >= 75][:5]
        return EngineResult(self.name, overall, side if status.startswith("BUY") else "WAIT", reasons or ["Cross-engine evidence remains mixed"], {
            "matrix": matrix,
            "overall_score": round(overall, 1),
            "trade_quality": round(trade_quality, 1),
            "grade": grade,
            "decision": status,
            "risk_level": "LOW" if safety_score >= 75 and risk_reward >= 65 else "MODERATE" if safety_score >= 50 else "HIGH",
        })


class AITradePlannerEngine(BaseEngine):
    """Create rule-based entries, stops, targets, sizing and exit conditions."""

    name = "AI Trade Planner"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        recommendation = market_data.get("recommendation", {})
        intelligence = market_data.get("intelligence", {})
        decision_matrix = market_data.get("decision_matrix_result")
        capital = max(_num(market_data.get("capital"), 200000), 0)
        risk_pct = float(np.clip(_num(market_data.get("risk_pct"), 1.0), .1, 5.0))
        lot_size = max(int(_num(market_data.get("lot_size"), 25)), 1)

        best = recommendation.get("best") or {}
        side = str(recommendation.get("side", "WAIT"))
        premium = _num(best.get("premium"))
        ask = _num(best.get("entry_trigger"), _num(best.get("ask"), premium))
        if not best or premium <= 0:
            return EngineResult(self.name, 0, "WAIT", ["No option contract passed the liquidity filters"], {
                "state": "WAIT", "plan": None, "rankings": []
            })

        price = intelligence.get("price", {}) or {}
        underlying_atr = max(_num(price.get("atr"), _num(price.get("close")) * .0025), 1.0)
        delta = max(_num(best.get("delta"), .5), .1)
        option_atr_proxy = max(premium * .06, underlying_atr * delta * .30)
        entry_mid = max(ask, premium * 1.005)
        entry_low = max(.05, entry_mid - option_atr_proxy * .12)
        entry_high = entry_mid + option_atr_proxy * .12
        stop_distance = max(option_atr_proxy * .70, entry_mid * .075)
        stop = max(.05, entry_low - stop_distance)
        risk_per_unit = max(entry_mid - stop, .05)
        target1 = entry_mid + risk_per_unit * 1.25
        target2 = entry_mid + risk_per_unit * 2.0
        target3 = entry_mid + risk_per_unit * 3.0
        risk_amount = capital * risk_pct / 100
        risk_per_lot = risk_per_unit * lot_size
        lots = int(math.floor(risk_amount / risk_per_lot)) if risk_per_lot > 0 else 0
        affordable_lots = int(math.floor(capital / max(entry_mid * lot_size, 1)))
        lots = max(0, min(lots, affordable_lots))
        exposure = lots * lot_size * entry_mid

        matrix_score = _num(getattr(decision_matrix, "score", 0), _num(recommendation.get("trade_quality"), 50))
        confirmed = bool(recommendation.get("confirmed")) and matrix_score >= 68
        state = "TRIGGERED" if confirmed else "WAITING"
        trigger_requirements = []
        if not recommendation.get("confirmed"):
            trigger_requirements.extend(recommendation.get("missing_conditions", [])[:4])
        if matrix_score < 68:
            trigger_requirements.append(f"Decision matrix must improve from {matrix_score:.0f} to 68+")
        trigger_requirements = list(dict.fromkeys(trigger_requirements))

        rankings_df = recommendation.get("rankings")
        rankings = []
        if isinstance(rankings_df, pd.DataFrame) and not rankings_df.empty:
            for _, row in rankings_df.head(5).iterrows():
                score = _num(row.get("final_score"))
                rankings.append({
                    "Contract": f"{_num(row.get('strike')):.0f} {row.get('side', side)}",
                    "Score": round(score, 1),
                    "Premium": round(_num(row.get("premium")), 2),
                    "Delta": round(_num(row.get("delta_abs")), 2),
                    "Spread %": round(_num(row.get("spread_pct")), 2),
                    "Liquidity": round(_num(row.get("liquidity_score")), 1),
                    "Flow": round(_num(row.get("flow_score")), 1),
                    "Verdict": "BEST" if len(rankings) == 0 else "GOOD" if score >= 70 else "WATCH" if score >= 60 else "AVOID",
                })

        exit_rules = [
            "Book partial profit at Target 1 and move stop toward entry",
            "Exit if institutional confirmation falls below 55",
            "Exit if price rejects VWAP and delta weakens",
            "Exit if opposite-side writing rises sharply or premium stalls",
        ]
        plan = {
            "state": state,
            "side": side,
            "contract": best.get("contract"),
            "strike": best.get("strike"),
            "entry_low": round(entry_low, 2),
            "entry_high": round(entry_high, 2),
            "confirmation_entry": round(entry_high, 2),
            "aggressive_entry": round(entry_low, 2),
            "stop_loss": round(stop, 2),
            "target1": round(target1, 2),
            "target2": round(target2, 2),
            "target3": round(target3, 2),
            "risk_per_unit": round(risk_per_unit, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_reward_t1": 1.25,
            "risk_reward_t2": 2.0,
            "risk_reward_t3": 3.0,
            "lots": lots,
            "lot_size": lot_size,
            "quantity": lots * lot_size,
            "exposure": round(exposure, 2),
            "trigger_requirements": trigger_requirements,
            "exit_rules": exit_rules,
            "holding_style": "Intraday momentum; reassess every candle",
        }
        score = _clip(matrix_score * .55 + _num(recommendation.get("confidence"), 50) * .30 + _num(best.get("score"), 50) * .15)
        reasons = recommendation.get("reasons", [])[:5] or ["Best available liquid contract selected"]
        return EngineResult(self.name, score, side if confirmed else "WAIT", reasons, {
            "state": state, "plan": plan, "rankings": rankings,
            "capital": capital, "risk_pct": risk_pct,
        })
