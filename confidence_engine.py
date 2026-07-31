from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_CONFIG_PATH = Path(__file__).with_name("confidence_config.json")


def _safe(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if not np.isfinite(number) else number
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


def load_confidence_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load confidence configuration: {config_path}: {exc}") from exc
    weights = config.get("weights", {})
    total = sum(_safe(value) for value in weights.values())
    if not weights or abs(total - 1.0) > 0.001:
        raise ValueError(f"Confidence weights must total 1.0; current total is {total:.4f}")
    return config


def confidence_label(score: float) -> str:
    if score >= 90: return "Exceptional"
    if score >= 80: return "High"
    if score >= 70: return "Good"
    if score >= 60: return "Moderate"
    if score >= 50: return "Low"
    return "Very Low"


def _consensus(component_scores: dict[str, float], direction: str, config: dict[str, Any]) -> dict[str, Any]:
    healthy = _safe(config["thresholds"].get("healthy"), 60)
    engines = []
    mapping = [
        ("Trend Engine", "Trend"),
        ("OI / Institutional Engine", "OI / Institutional Flow"),
        ("Volume Engine", "Volume"),
        ("Premium Flow Engine", "Premium Flow"),
        ("Greeks Engine", "Greeks"),
        ("Liquidity Engine", "Liquidity"),
        ("Risk Engine", "Risk / Reward"),
    ]
    for engine, key in mapping:
        score = _clip(_safe(component_scores.get(key), 50))
        if score >= healthy:
            vote = direction
            agrees = True
        elif score < 45:
            vote = "PE" if direction == "CE" else "CE"
            agrees = False
        else:
            vote = "NEUTRAL"
            agrees = False
        engines.append({"engine": engine, "score": score, "vote": vote, "agrees": agrees})
    agreeing = sum(int(item["agrees"]) for item in engines)
    return {"engines": engines, "agreeing": agreeing, "total": len(engines), "ratio": agreeing / max(len(engines), 1) * 100}


def build_confidence(*, intelligence: dict[str, Any], component_scores: dict[str, float], regime: dict[str, Any], best_row: Any | None, blockers: list[str], option_rows: int, direction: str = "CE", config_path: str | Path | None = None) -> dict[str, Any]:
    config = load_confidence_config(config_path)
    weights = config["weights"]
    thresholds = config["thresholds"]
    adjustments = config["adjustments"]
    caps = config["caps"]

    values = {
        "Underlying trend": _clip(_safe(component_scores.get("Trend"), 50)),
        "OI / institutional flow": _clip(_safe(component_scores.get("OI / Institutional Flow"), 50)),
        "Volume participation": _clip(_safe(component_scores.get("Volume"), 50)),
        "Premium confirmation": _clip(_safe(component_scores.get("Premium Flow"), 50)),
        "Greeks responsiveness": _clip(_safe(component_scores.get("Greeks"), 50)),
        "Liquidity": _clip(_safe(component_scores.get("Liquidity"), 50)),
        "Risk / reward": _clip(_safe(component_scores.get("Risk / Reward"), 50)),
        "Base model agreement": _clip(_safe(intelligence.get("confidence"), 50)),
    }
    raw = sum(values[name] * _safe(weight) for name, weight in weights.items())
    core = [values["Underlying trend"], values["OI / institutional flow"], values["Volume participation"], values["Premium confirmation"]]
    strong = sum(value >= _safe(thresholds["core_strong"], 70) for value in core)
    weak = sum(value < _safe(thresholds["core_weak"], 50) for value in core)
    raw += strong * _safe(adjustments["strong_core_bonus"], 2) - weak * _safe(adjustments["weak_core_penalty"], 3.5)

    deductions, bonuses = [], []
    cap = 100.0
    rvol = _safe(regime.get("relative_volume"), 1)
    if strong >= 3: bonuses.append(f"{strong}/4 core directional components are strongly aligned")
    if rvol >= 1.5:
        raw += _safe(adjustments["high_rvol_bonus"], 2)
        bonuses.append(f"Relative volume confirms participation at {rvol:.2f}×")
    elif rvol < 0.8:
        raw -= _safe(adjustments["low_rvol_penalty"], 8)
        cap = min(cap, _safe(caps["low_relative_volume"], 69))
        deductions.append(f"Relative volume is weak at {rvol:.2f}×")
    if weak >= 2:
        cap = min(cap, _safe(caps["multiple_weak_core"], 64)); deductions.append(f"{weak}/4 core directional components remain weak")
    if best_row is None:
        cap = min(cap, _safe(caps["no_contract"], 49)); deductions.append("No tradeable contract passed the contract filters")
    else:
        spread = _safe(best_row.get("spread_pct"), 100); contract_score = _safe(best_row.get("final_score"), 0)
        if spread > 5:
            raw -= _safe(adjustments["wide_spread_penalty"], 5); deductions.append(f"Best contract spread is wide at {spread:.2f}%")
        if contract_score < 62:
            cap = min(cap, _safe(caps["low_contract_quality"], 64)); deductions.append(f"Best contract quality is below trigger threshold ({contract_score:.1f}/62)")
    if option_rows < 5:
        cap = min(cap, _safe(caps["small_option_sample"], 55)); deductions.append("Option-chain sample is too small for high confidence")
    if regime.get("name") in {"Range-bound / Compressed", "Low-Participation"}:
        cap = min(cap, _safe(caps["bad_regime"], 59)); deductions.append(f"Market regime is {regime.get('name')}")
    if blockers:
        cap = min(cap, _safe(caps["hard_blocker"], 49)); deductions.append(f"{len(blockers)} active no-trade blocker(s)")

    score = min(_clip(raw), cap)
    margin = 5 if score >= 80 else 8 if score >= 65 else 12
    contributions = [{"name": name, "score": values[name], "weight": weights[name] * 100, "points": values[name] * weights[name], "passed": values[name] >= _safe(thresholds["healthy"], 60)} for name in weights]
    consensus = _consensus(component_scores, direction, config)
    market_confidence = _clip((values["Underlying trend"] * 0.35 + values["Volume participation"] * 0.25 + values["Base model agreement"] * 0.25 + (100 if regime.get("name") not in {"Range-bound / Compressed", "Low-Participation"} else 35) * 0.15))
    direction_confidence = _clip(values["Underlying trend"] * 0.30 + values["OI / institutional flow"] * 0.35 + values["Premium confirmation"] * 0.20 + consensus["ratio"] * 0.15)
    trigger_confidence = _clip(score * 0.65 + values["Liquidity"] * 0.15 + values["Risk / reward"] * 0.10 + consensus["ratio"] * 0.10)
    return {
        "score": score, "label": confidence_label(score), "raw_score": _clip(raw), "cap": cap,
        "lower_bound": max(0, score-margin), "upper_bound": min(cap, score+margin),
        "strong_core_signals": strong, "weak_core_signals": weak, "contributions": contributions,
        "bonuses": bonuses, "deductions": list(dict.fromkeys(deductions)),
        "method": "Configurable weighted agreement with conservative risk and data-quality caps",
        "config_version": str(config.get("version", "unknown")), "market_confidence": market_confidence,
        "direction_confidence": direction_confidence, "trigger_confidence": trigger_confidence,
        "consensus": consensus,
    }


def candidate_confidence(row: Any, market_confidence: float, active_side: bool) -> float:
    contract = (_safe(row.get("final_score")) * .30 + _safe(row.get("flow_score")) * .22 + _safe(row.get("liquidity_score")) * .20 + _safe(row.get("responsiveness_score")) * .16 + _safe(row.get("risk_score")) * .12)
    return _clip(contract * .55 + market_confidence * .45 * (1 if active_side else .72))
