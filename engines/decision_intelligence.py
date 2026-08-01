from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from .base_engine import BaseEngine, EngineResult


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if np.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


def _vote(value: Any) -> str:
    text = str(value or "WAIT").upper()
    if "CE" in text or text in {"BUY", "BULLISH"}:
        return "CE"
    if "PE" in text or text in {"SELL", "BEARISH"}:
        return "PE"
    return "WAIT"


@dataclass
class DecisionPackage:
    recommendation: str
    confidence: float
    probability: float
    probabilities: dict[str, float]
    consensus: float
    conflict_score: float
    conflict_level: str
    risk_level: str
    risk_veto: bool
    status: str
    market_regime: str
    opportunity_stage: str
    playbook: str
    entry: dict[str, Any] = field(default_factory=dict)
    stop_loss: float | None = None
    targets: list[float] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    invalidation: list[str] = field(default_factory=list)
    reasoning_trace: list[str] = field(default_factory=list)
    votes: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIConsensusEngine(BaseEngine):
    name = "AI Consensus Engine"

    DEFAULT_WEIGHTS = {
        "Market Regime": 0.10,
        "Institutional Flow": 0.16,
        "Smart Money Index": 0.12,
        "Market Energy": 0.08,
        "OI / Base Decision": 0.12,
        "Greeks / Decision Matrix": 0.10,
        "Candle DNA": 0.08,
        "Pattern AI": 0.06,
        "Historical Similarity": 0.08,
        "Institutional Playbook": 0.05,
        "Signal Validation": 0.05,
    }

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        recommendation = market_data.get("recommendation", {}) or {}
        matrix = market_data.get("decision_matrix_result")
        validation = market_data.get("validation_result")
        engines = [
            ("Market Regime", market_data.get("regime_result")),
            ("Institutional Flow", market_data.get("flow_result")),
            ("Smart Money Index", market_data.get("smi_result")),
            ("Market Energy", market_data.get("energy_result")),
            ("OI / Base Decision", None),
            ("Greeks / Decision Matrix", matrix),
            ("Candle DNA", market_data.get("candle_dna_result")),
            ("Pattern AI", market_data.get("pattern_result")),
            ("Historical Similarity", market_data.get("similarity_result")),
            ("Institutional Playbook", market_data.get("playbook_result")),
            ("Signal Validation", validation),
        ]
        rows: list[dict[str, Any]] = []
        totals = {"CE": 0.0, "PE": 0.0, "WAIT": 0.0}
        available_weight = 0.0
        base_side = _vote(recommendation.get("side"))
        base_score = _num(recommendation.get("confidence"), _num(recommendation.get("combined_score"), 50))
        for name, result in engines:
            weight = self.DEFAULT_WEIGHTS[name]
            if name == "OI / Base Decision":
                vote, confidence, available = base_side, base_score, True
            elif result is None:
                vote, confidence, available = "WAIT", 0.0, False
            else:
                vote = _vote(getattr(result, "vote", "WAIT"))
                confidence = _clip(_num(getattr(result, "score", 0)))
                available = True
            if available:
                available_weight += weight
                totals[vote] += weight * max(confidence, 20.0) / 100.0
            rows.append({
                "Engine": name, "Vote": vote, "Confidence %": round(confidence, 1),
                "Weight %": round(weight * 100, 1), "Available": available,
            })
        denominator = sum(totals.values()) or 1.0
        shares = {key: value / denominator * 100 for key, value in totals.items()}
        direction = max(("CE", "PE"), key=lambda key: shares[key])
        directional_agreement = shares[direction]
        missing = max(0.0, 1.0 - available_weight) * 100
        # 0 means clean directional alignment; 100 means a split or mostly-WAIT committee.
        directional_split = 100.0 - abs(shares["CE"] - shares["PE"])
        conflict = _clip(directional_split * 0.70 + shares["WAIT"] * 0.30)
        level = "CRITICAL" if conflict >= 70 else "HIGH" if conflict >= 50 else "MEDIUM" if conflict >= 30 else "LOW"
        consensus = _clip(directional_agreement - conflict * 0.25 - missing * 0.35)
        final_vote = direction if consensus >= 62 and shares[direction] >= 55 else "WAIT"
        reasons = [
            f"{direction} has {shares[direction]:.1f}% of confidence-weighted votes.",
            f"Conflict is {level} at {conflict:.1f}%.",
            f"Missing evidence penalty is {missing:.1f}%.",
        ]
        return EngineResult(self.name, consensus, final_vote, reasons, {
            "consensus": round(consensus, 1), "vote_shares": {k: round(v, 1) for k, v in shares.items()},
            "conflict_score": round(conflict, 1), "conflict_level": level,
            "missing_evidence": round(missing, 1), "votes": rows,
        })


class TradeProbabilityEngine(BaseEngine):
    name = "Trade Probability Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        consensus = market_data.get("consensus_result")
        similarity = market_data.get("similarity_result")
        validation = market_data.get("validation_result")
        cmeta = getattr(consensus, "metadata", {}) or {}
        shares = cmeta.get("vote_shares", {}) or {}
        ce = _num(shares.get("CE"), 0)
        pe = _num(shares.get("PE"), 0)
        wait = _num(shares.get("WAIT"), 0)
        hist_vote = _vote(getattr(similarity, "vote", "WAIT"))
        hist_score = _num(getattr(similarity, "score", 0))
        if hist_vote == "CE": ce += hist_score * 0.08
        elif hist_vote == "PE": pe += hist_score * 0.08
        validated = bool(getattr(validation, "metadata", {}).get("validated", False))
        if not validated:
            wait += 18
        conflict = _num(cmeta.get("conflict_score"))
        wait += conflict * 0.22
        raw = np.array([max(ce, 1), max(pe, 1), max(wait, 1)], dtype=float)
        probs = raw / raw.sum() * 100
        probabilities = {"BUY CE": round(float(probs[0]), 1), "BUY PE": round(float(probs[1]), 1), "WAIT": round(float(probs[2]), 1)}
        best = max(probabilities, key=probabilities.get)
        vote = "CE" if best == "BUY CE" else "PE" if best == "BUY PE" else "WAIT"
        confidence = probabilities[best]
        return EngineResult(self.name, confidence, vote, [
            f"BUY CE probability: {probabilities['BUY CE']:.1f}%.",
            f"BUY PE probability: {probabilities['BUY PE']:.1f}%.",
            f"WAIT probability: {probabilities['WAIT']:.1f}%.",
        ], {"probabilities": probabilities, "leading_outcome": best, "probability": confidence})


class EnhancedRiskValidationEngine(BaseEngine):
    name = "Enhanced Risk Validation Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        recommendation = market_data.get("recommendation", {}) or {}
        consensus = market_data.get("consensus_result")
        probability = market_data.get("probability_result")
        validation = market_data.get("validation_result")
        stability = market_data.get("stability_result")
        false_breakout = market_data.get("false_breakout_result")
        confirmation = market_data.get("confirmation_result")
        plan = getattr(market_data.get("trade_plan_result"), "metadata", {}).get("plan") or {}
        checks: list[dict[str, Any]] = []
        def add(name: str, passed: bool, critical: bool, detail: str) -> None:
            checks.append({"Check": name, "Passed": bool(passed), "Critical": critical, "Detail": detail})
        add("Consensus", _num(getattr(consensus, "score", 0)) >= 62, True, f"{_num(getattr(consensus, 'score', 0)):.1f}%")
        add("Probability", _num(getattr(probability, "score", 0)) >= 50, False, f"{_num(getattr(probability, 'score', 0)):.1f}%")
        add("Signal validation", bool(getattr(validation, "metadata", {}).get("validated", False)), True, str(getattr(validation, "metadata", {}).get("decision", "WAIT")))
        add("Recommendation stability", bool(getattr(stability, "metadata", {}).get("passed", False)), True, f"{_num(getattr(stability, 'score', 0)):.1f}%")
        add("False-breakout safety", not bool(getattr(false_breakout, "metadata", {}).get("blocked", False)), True, f"risk {_num(getattr(false_breakout, 'score', 0)):.1f}")
        add("Institutional confirmation", str(getattr(confirmation, "metadata", {}).get("status", "")) == "CONFIRMED", True, str(getattr(confirmation, "metadata", {}).get("status", "DEVELOPING")))
        add("Base recommendation confirmed", bool(recommendation.get("confirmed", False)), True, str(recommendation.get("status", "WAIT")))
        if plan:
            risk_per_unit = max(_num(plan.get("entry_high")) - _num(plan.get("stop_loss")), 0)
            reward = max(_num(plan.get("target2")) - _num(plan.get("entry_high")), 0)
            rr = reward / risk_per_unit if risk_per_unit > 0 else 0
            add("Reward/Risk", rr >= 1.5, False, f"{rr:.2f}R")
            add("Position available", _num(plan.get("quantity")) > 0, False, f"Qty {int(_num(plan.get('quantity')))}")
        else:
            add("Trade plan", False, False, "No actionable plan")
        failed_critical = [c for c in checks if c["Critical"] and not c["Passed"]]
        failed = [c for c in checks if not c["Passed"]]
        veto = bool(failed_critical)
        passed = len(checks) - len(failed)
        score = _clip(passed / max(len(checks), 1) * 100)
        risk_level = "CRITICAL" if len(failed_critical) >= 3 else "HIGH" if veto else "MEDIUM" if failed else "LOW"
        blockers = [f"{c['Check']}: {c['Detail']}" for c in failed]
        vote = "WAIT" if veto else _vote(getattr(consensus, "vote", "WAIT"))
        return EngineResult(self.name, score, vote, blockers or ["All configured risk checks passed."], {
            "veto": veto, "risk_level": risk_level, "checks": checks, "passed": passed,
            "total": len(checks), "blockers": blockers,
        })


class DecisionReasoningEngine(BaseEngine):
    name = "Decision Reasoning Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        consensus = market_data.get("consensus_result")
        risk = market_data.get("risk_result")
        recommendation = market_data.get("recommendation", {}) or {}
        votes = getattr(consensus, "metadata", {}).get("votes", [])
        target = _vote(getattr(consensus, "vote", "WAIT"))
        positive = [row for row in votes if row.get("Vote") == target and row.get("Confidence %", 0) >= 55]
        positive.sort(key=lambda row: row.get("Confidence %", 0) * row.get("Weight %", 0), reverse=True)
        trace = [f"{row['Engine']} ({row['Confidence %']:.0f}%)" for row in positive[:7]]
        if bool(getattr(risk, "metadata", {}).get("veto", False)):
            trace += ["Risk veto", "WAIT"]
            vote = "WAIT"
        else:
            trace += ["Consensus confirmed", f"BUY {target}" if target in {"CE", "PE"} else "WAIT"]
            vote = target
        evidence = [row["Engine"] for row in positive]
        blockers = getattr(risk, "metadata", {}).get("blockers", [])
        score = _num(getattr(consensus, "score", 0)) * (0.7 if blockers else 1.0)
        return EngineResult(self.name, score, vote, trace, {
            "trace": trace, "evidence": evidence, "blockers": blockers,
            "base_status": recommendation.get("status", "WAIT"),
        })


class InvalidationEngine(BaseEngine):
    name = "Invalidation Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        side = _vote(getattr(market_data.get("consensus_result"), "vote", "WAIT"))
        rules = [
            "Institutional confidence falls below 65%",
            "Market Energy falls below 55%",
            "Signal validation loses a critical control",
            "False-breakout risk becomes active",
        ]
        if side == "CE":
            rules = ["Price closes below VWAP/support", "Put writing weakens or call writing accelerates", "Delta/gamma flow turns bearish"] + rules
        elif side == "PE":
            rules = ["Price closes above VWAP/resistance", "Call writing weakens or put writing accelerates", "Delta/gamma flow turns bullish"] + rules
        return EngineResult(self.name, 100.0 if side != "WAIT" else 50.0, "WAIT", rules, {"rules": rules, "side": side})


class DecisionPackageEngine(BaseEngine):
    name = "Decision Package Engine"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        consensus = market_data.get("consensus_result")
        probability = market_data.get("probability_result")
        risk = market_data.get("risk_result")
        reasoning = market_data.get("reasoning_result")
        invalidation = market_data.get("invalidation_result")
        recommendation = market_data.get("recommendation", {}) or {}
        risk_meta = getattr(risk, "metadata", {}) or {}
        prob_meta = getattr(probability, "metadata", {}) or {}
        cmeta = getattr(consensus, "metadata", {}) or {}
        veto = bool(risk_meta.get("veto", False))
        consensus_vote = _vote(getattr(consensus, "vote", "WAIT"))
        final = "WAIT" if veto or consensus_vote == "WAIT" else f"BUY {consensus_vote}"
        confidence = _clip((_num(getattr(consensus, "score", 0)) * 0.55) + (_num(getattr(risk, "score", 0)) * 0.25) + (_num(getattr(probability, "score", 0)) * 0.20))
        plan = getattr(market_data.get("trade_plan_result"), "metadata", {}).get("plan") or {}
        entry = {"low": plan.get("entry_low"), "high": plan.get("entry_high"), "contract": plan.get("contract")}
        targets = [plan.get("target1"), plan.get("target2"), plan.get("target3")]
        targets = [float(v) for v in targets if v is not None]
        regime = getattr(market_data.get("regime_result"), "metadata", {}).get("regime", "Unknown")
        opportunity = getattr(market_data.get("opportunity_result"), "metadata", {}).get("stage", "SCANNING")
        playbook = getattr(market_data.get("playbook_result"), "metadata", {}).get("primary", {}).get("Playbook", "Developing")
        package = DecisionPackage(
            recommendation=final,
            confidence=round(confidence, 1),
            probability=round(_num(prob_meta.get("probability")), 1),
            probabilities=prob_meta.get("probabilities", {}),
            consensus=round(_num(cmeta.get("consensus")), 1),
            conflict_score=round(_num(cmeta.get("conflict_score")), 1),
            conflict_level=str(cmeta.get("conflict_level", "LOW")),
            risk_level=str(risk_meta.get("risk_level", "HIGH")),
            risk_veto=veto,
            status="BLOCKED" if veto else "ACTIONABLE" if final != "WAIT" else "WAITING",
            market_regime=str(regime), opportunity_stage=str(opportunity), playbook=str(playbook),
            entry=entry, stop_loss=plan.get("stop_loss"), targets=targets,
            evidence=getattr(reasoning, "metadata", {}).get("evidence", []),
            blockers=risk_meta.get("blockers", []),
            invalidation=getattr(invalidation, "metadata", {}).get("rules", []),
            reasoning_trace=getattr(reasoning, "metadata", {}).get("trace", []),
            votes=cmeta.get("votes", []),
        )
        metadata = package.to_dict()
        metadata["legacy_recommendation"] = recommendation.get("side", "WAIT")
        return EngineResult(self.name, confidence, _vote(final), [f"Final decision: {final}.", f"Risk: {package.risk_level}."], metadata)
