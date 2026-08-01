from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from confidence_engine import build_confidence, candidate_confidence, confidence_label


def _safe(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if not np.isfinite(number) else number
    except (TypeError, ValueError):
        return default


def _normalize(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return pd.Series(50.0, index=values.index)
    return (values - low) / (high - low) * 100.0


def detect_market_regime(price: dict[str, Any], intelligence: dict[str, Any]) -> dict[str, Any]:
    candles = price["candles"].copy()
    latest = candles.iloc[-1]
    atr = max(_safe(price.get("atr")), 1.0)
    ema_gap = abs(_safe(price.get("ema9")) - _safe(price.get("ema21"))) / atr
    distance_vwap = abs(_safe(price.get("close")) - _safe(price.get("vwap"))) / atr

    recent = candles.tail(min(12, len(candles)))
    range_width = _safe(recent["high"].max() - recent["low"].min()) / atr
    volume = pd.to_numeric(candles["volume"], errors="coerce").fillna(0.0)
    baseline = _safe(volume.tail(min(21, len(volume))).iloc[:-1].median()) if len(volume) > 1 else 0.0
    rvol = _safe(latest.get("volume")) / baseline if baseline > 0 else 1.0

    score = _safe(intelligence.get("score"))
    if abs(score) >= 3.5 and ema_gap >= 0.35 and distance_vwap >= 0.35:
        regime = "Trending Up" if score > 0 else "Trending Down"
    elif rvol >= 1.8 and range_width >= 2.0:
        regime = "High-Participation Expansion"
    elif range_width <= 1.4 and ema_gap <= 0.2:
        regime = "Range-bound / Compressed"
    elif rvol < 0.7:
        regime = "Low-Participation"
    else:
        regime = "Developing Trend"

    return {
        "name": regime,
        "relative_volume": float(np.clip(rvol, 0, 20)),
        "ema_gap_atr": ema_gap,
        "range_atr": range_width,
    }


def _side_columns(side: str) -> dict[str, str]:
    prefix = "call" if side == "CE" else "put"
    return {
        "ltp": f"{prefix}_ltp",
        "bid": f"{prefix}_bid",
        "ask": f"{prefix}_ask",
        "oi": f"{prefix}_oi",
        "oi_change": f"{prefix}_oi_change",
        "volume": f"{prefix}_volume",
        "iv": f"{prefix}_iv",
        "delta": f"{prefix}_delta",
        "gamma": f"{prefix}_gamma",
        "theta": f"{prefix}_theta",
        "price_change": f"{prefix}_price_change",
        "instrument_key": f"{prefix}_instrument_key",
    }


def rank_strikes(
    chain: pd.DataFrame,
    side: str,
    spot: float,
    direction_strength: float,
) -> pd.DataFrame:
    cols = _side_columns(side)
    ranked = chain.copy()
    for column in cols.values():
        if column not in ranked.columns:
            ranked[column] = 0.0

    ltp = pd.to_numeric(ranked[cols["ltp"]], errors="coerce").fillna(0.0)
    bid = pd.to_numeric(ranked[cols["bid"]], errors="coerce").fillna(0.0)
    ask = pd.to_numeric(ranked[cols["ask"]], errors="coerce").fillna(0.0)
    spread_pct = ((ask - bid).clip(lower=0) / ltp.replace(0, np.nan) * 100).fillna(100.0)
    abs_delta = pd.to_numeric(ranked[cols["delta"]], errors="coerce").abs().fillna(0.0)
    distance_pct = (pd.to_numeric(ranked["strike"], errors="coerce") - spot).abs() / max(spot, 1) * 100

    volume_score = _normalize(ranked[cols["volume"]])
    oi_score = _normalize(ranked[cols["oi"]])
    oi_change_score = _normalize(ranked[cols["oi_change"]].clip(lower=0))
    gamma_score = _normalize(ranked[cols["gamma"]].abs())
    momentum_score = _normalize(ranked[cols["price_change"]])

    # Intraday option buying normally benefits from responsive ATM/near-ITM contracts.
    delta_score = (100 - (abs_delta - 0.55).abs() / 0.55 * 100).clip(0, 100)
    spread_score = (100 - spread_pct * 8).clip(0, 100)
    distance_score = (100 - distance_pct * 45).clip(0, 100)
    theta = pd.to_numeric(ranked[cols["theta"]], errors="coerce").abs().fillna(0.0)
    theta_score = (100 - _normalize(theta)).clip(0, 100)

    ranked["liquidity_score"] = volume_score * 0.45 + oi_score * 0.30 + spread_score * 0.25
    ranked["responsiveness_score"] = delta_score * 0.55 + gamma_score * 0.25 + distance_score * 0.20
    ranked["flow_score"] = momentum_score * 0.45 + oi_change_score * 0.30 + volume_score * 0.25
    ranked["risk_score"] = spread_score * 0.45 + theta_score * 0.30 + distance_score * 0.25
    ranked["final_score"] = (
        ranked["liquidity_score"] * 0.32
        + ranked["responsiveness_score"] * 0.28
        + ranked["flow_score"] * 0.25
        + ranked["risk_score"] * 0.15
    )
    ranked["final_score"] *= 0.85 + min(abs(direction_strength), 6.0) / 6.0 * 0.15

    valid = (ltp > 0) & (bid > 0) & (ask > 0) & (spread_pct <= 8) & (abs_delta.between(0.25, 0.80))
    ranked = ranked.loc[valid].copy()
    ranked["side"] = side
    ranked["premium"] = ltp.loc[ranked.index]
    ranked["bid"] = bid.loc[ranked.index]
    ranked["ask"] = ask.loc[ranked.index]
    ranked["spread_pct"] = spread_pct.loc[ranked.index]
    ranked["delta_abs"] = abs_delta.loc[ranked.index]
    ranked["volume"] = pd.to_numeric(ranked[cols["volume"]], errors="coerce").fillna(0.0)
    ranked["oi"] = pd.to_numeric(ranked[cols["oi"]], errors="coerce").fillna(0.0)
    ranked["oi_change"] = pd.to_numeric(ranked[cols["oi_change"]], errors="coerce").fillna(0.0)
    ranked["instrument_key"] = ranked[cols["instrument_key"]]
    return ranked.sort_values("final_score", ascending=False).reset_index(drop=True)



def _decorate_trade_candidates(
    rankings: pd.DataFrame,
    active_side: str,
    confirmed: bool,
    market_confidence: float,
) -> pd.DataFrame:
    """Add planning levels and a clear WAITING/TRIGGERED state to ranked contracts."""
    if rankings.empty:
        return rankings.copy()

    result = rankings.head(5).copy()
    result["entry_trigger"] = np.maximum(result["ask"], result["premium"] * 1.01)
    result["stop_loss"] = (result["entry_trigger"] * 0.90).clip(lower=0.05)
    result["target1"] = result["entry_trigger"] * 1.14
    result["target2"] = result["entry_trigger"] * 1.26
    result["trade_state"] = "WAITING"
    result["candidate_confidence"] = result.apply(
        lambda row: candidate_confidence(row, market_confidence, str(row.get("side")) == active_side), axis=1
    )
    result["confidence_band"] = result["candidate_confidence"].map(confidence_label)

    trigger_mask = (
        (result["side"] == active_side)
        & confirmed
        & (result["final_score"] >= 62)
        & (result["flow_score"] >= 50)
        & (result["liquidity_score"] >= 50)
    )
    result.loc[trigger_mask, "trade_state"] = "TRIGGERED"
    return result


def _component_scores(
    option_result: dict[str, Any],
    intelligence: dict[str, Any],
    institutional: dict[str, Any] | None,
    regime: dict[str, Any],
    best_row: pd.Series | None,
) -> dict[str, float]:
    """Return transparent 0-100 component scores used by the health meter."""
    summary = option_result["summary"]
    score = _safe(intelligence.get("score"))
    direction_sign = 1.0 if score >= 0 else -1.0
    option_score = _safe(summary.get("score")) * direction_sign
    price_score = _safe(intelligence.get("price", {}).get("score")) * direction_sign
    flow_strength = _safe((institutional or {}).get("primary_strength")) * direction_sign
    rvol = _safe(regime.get("relative_volume"), 1.0)

    trend = float(np.clip(50 + price_score * 9, 0, 100))
    oi = float(np.clip(50 + option_score * 8 + flow_strength * 0.25, 0, 100))
    volume = float(np.clip(35 + rvol * 30, 0, 100))
    premium = float(np.clip(_safe(best_row.get("flow_score") if best_row is not None else 0), 0, 100))
    liquidity = float(np.clip(_safe(best_row.get("liquidity_score") if best_row is not None else 0), 0, 100))
    greeks = float(np.clip(_safe(best_row.get("responsiveness_score") if best_row is not None else 0), 0, 100))
    risk = float(np.clip(_safe(best_row.get("risk_score") if best_row is not None else 0), 0, 100))
    return {
        "Trend": trend,
        "OI / Institutional Flow": oi,
        "Volume": volume,
        "Premium Flow": premium,
        "Greeks": greeks,
        "Liquidity": liquidity,
        "Risk / Reward": risk,
    }


def _directional_confidence(score: float) -> float:
    """Normalize the legacy directional score so the old 2.60 gate equals 75/100."""
    return float(np.clip(abs(score) / 2.60 * 75.0, 0.0, 100.0))


def _side_strength(rankings: pd.DataFrame, side: str, score: float, components: dict[str, float]) -> float:
    """Score CE and PE independently using contract quality, flow and directional alignment."""
    if rankings.empty:
        return 0.0
    row = rankings.iloc[0]
    contract = _safe(row.get("final_score"))
    flow = _safe(row.get("flow_score"))
    liquidity = _safe(row.get("liquidity_score"))
    responsiveness = _safe(row.get("responsiveness_score"))
    signed_alignment = score if side == "CE" else -score
    direction = float(np.clip(50.0 + signed_alignment / 6.0 * 50.0, 0.0, 100.0))
    institutional = _safe(components.get("OI / Institutional Flow"), 50.0)
    return float(np.clip(
        contract * 0.30 + flow * 0.20 + liquidity * 0.15
        + responsiveness * 0.10 + direction * 0.20 + institutional * 0.05,
        0.0, 100.0,
    ))


def _early_move_detector(
    score: float,
    regime: dict[str, Any],
    components: dict[str, float],
    ce_strength: float,
    pe_strength: float,
) -> dict[str, Any]:
    """Informational buildup detector. It never authorizes an entry."""
    winner = "CE" if ce_strength >= pe_strength else "PE"
    side_strength = max(ce_strength, pe_strength)
    rvol_score = float(np.clip(_safe(regime.get("relative_volume"), 0.0) / 1.5 * 100.0, 0.0, 100.0))
    direction_build = _directional_confidence(score)
    probability = float(np.clip(
        side_strength * 0.30
        + _safe(components.get("OI / Institutional Flow"), 50) * 0.20
        + _safe(components.get("Premium Flow"), 50) * 0.15
        + _safe(components.get("Greeks"), 50) * 0.15
        + rvol_score * 0.10
        + direction_build * 0.10,
        0.0, 100.0,
    ))
    if probability >= 80:
        state = "STRONG BUILDUP"
    elif probability >= 65:
        state = "BUILDUP"
    elif probability >= 50:
        state = "MONITORING"
    else:
        state = "NO EARLY EDGE"
    return {
        "side": winner,
        "probability": probability,
        "state": state,
        "informational_only": True,
    }


def _condition_checklist(
    directional_confidence: float,
    trade_readiness: float,
    recommended_side: str,
    confidence: float,
    regime: dict[str, Any],
    best_row: pd.Series | None,
    blockers: list[str],
    ce_strength: float,
    pe_strength: float,
    strength_advantage: float,
) -> list[dict[str, Any]]:
    direction_label = "Confirmed" if directional_confidence >= 75 else "Building" if directional_confidence >= 50 else "No clear direction"
    checks = [
        {"name": "Directional confidence", "passed": directional_confidence >= 75, "detail": f"{directional_confidence:.0f} / 100 ({direction_label})"},
        {"name": "Trade readiness", "passed": trade_readiness >= 80, "detail": f"{trade_readiness:.0f} / 100"},
        {"name": "Recommended side", "passed": recommended_side in {"CE", "PE"} and strength_advantage >= 20, "detail": f"{recommended_side} • CE {ce_strength:.0f}% vs PE {pe_strength:.0f}%" if recommended_side in {"CE", "PE"} else "WAIT • no clear edge"},
        {"name": "Recommendation confidence", "passed": confidence >= 70, "detail": f"{confidence:.0f}% / 70%"},
        {"name": "Volume participation", "passed": _safe(regime.get("relative_volume"), 0) >= 0.8, "detail": f"{_safe(regime.get('relative_volume')):.2f}× / 0.80×"},
        {"name": "Tradeable regime", "passed": regime.get("name") not in {"Range-bound / Compressed", "Low-Participation"}, "detail": str(regime.get("name"))},
        {"name": "Contract quality", "passed": best_row is not None and _safe(best_row.get("final_score")) >= 62, "detail": f"{_safe(best_row.get('final_score') if best_row is not None else 0):.1f} / 62"},
        {"name": "No hard blocker", "passed": not blockers, "detail": "Clear" if not blockers else f"{len(blockers)} blocker(s)"},
    ]
    return checks

def build_recommendation(
    option_result: dict[str, Any],
    intelligence: dict[str, Any],
    institutional: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = option_result["summary"]
    chain = option_result["chain"]
    price = intelligence["price"]
    score = _safe(intelligence.get("score"))
    confidence = _safe(intelligence.get("confidence"), 50)
    regime = detect_market_regime(price, intelligence)
    flow_strength = _safe((institutional or {}).get("primary_strength"))

    bullish = score > 0
    direction = "Bullish" if bullish else "Bearish"
    ce_rankings = rank_strikes(chain, "CE", _safe(summary["spot"]), score)
    pe_rankings = rank_strikes(chain, "PE", _safe(summary["spot"]), score)
    # Initial side is directional; final side is selected after independent CE/PE strength scoring.
    side = "CE" if bullish else "PE"
    rankings = ce_rankings if side == "CE" else pe_rankings

    reasons: list[str] = []
    blockers: list[str] = list(intelligence.get("no_trade_reasons", []))
    rvol = regime["relative_volume"]
    if rvol >= 1.5:
        reasons.append(f"Underlying relative volume is elevated at {rvol:.1f}× its recent median")
    elif rvol < 0.75:
        blockers.append("Underlying participation is below its recent median")

    if institutional:
        if bullish and flow_strength >= 20:
            reasons.append("Stored OI-flow history supports the bullish direction")
        elif not bullish and flow_strength <= -20:
            reasons.append("Stored OI-flow history supports the bearish direction")
        elif abs(flow_strength) >= 20:
            blockers.append("Historical institutional-flow direction conflicts with the current setup")

    reasons.extend(intelligence.get("evidence", [])[:5])
    if rankings.empty:
        blockers.append("No nearby contract passed liquidity, spread and delta filters")

    best_row = rankings.iloc[0] if not rankings.empty else None
    components = _component_scores(option_result, intelligence, institutional, regime, best_row)
    confidence_detail = build_confidence(
        intelligence=intelligence,
        component_scores=components,
        regime=regime,
        best_row=best_row,
        blockers=blockers,
        option_rows=len(chain),
        direction=side,
    )
    confidence = confidence_detail["score"]

    directional_confidence = _directional_confidence(score)
    ce_strength = _side_strength(ce_rankings, "CE", score, components)
    pe_strength = _side_strength(pe_rankings, "PE", score, components)
    strength_advantage = abs(ce_strength - pe_strength)
    recommended_side = "CE" if ce_strength > pe_strength else "PE"
    if strength_advantage < 10:
        recommended_side = "WAIT"

    side = recommended_side if recommended_side in {"CE", "PE"} else ("CE" if bullish else "PE")
    direction = "Bullish" if side == "CE" else "Bearish"
    rankings = ce_rankings if side == "CE" else pe_rankings
    best_row = rankings.iloc[0] if not rankings.empty else None
    selected_strength = max(ce_strength, pe_strength)
    regime_ready = regime["name"] not in {"Range-bound / Compressed", "Low-Participation"}
    trade_readiness = float(np.clip(
        directional_confidence * 0.35
        + selected_strength * 0.30
        + confidence * 0.25
        + (100.0 if rvol >= 0.8 and regime_ready else 35.0) * 0.10
        - (20.0 if blockers else 0.0),
        0.0, 100.0,
    ))
    early_move = _early_move_detector(score, regime, components, ce_strength, pe_strength)

    confirmed = (
        not blockers
        and directional_confidence >= 75
        and trade_readiness >= 80
        and selected_strength >= 80
        and strength_advantage >= 20
        and confidence >= 70
        and rvol >= 0.8
        and regime_ready
        and not rankings.empty
        and _safe(rankings.iloc[0]["final_score"]) >= 62
    )

    if blockers or directional_confidence < 40:
        status = "NO TRADE"
    elif confirmed:
        status = f"READY — BUY {side}"
    elif recommended_side == "WAIT" or strength_advantage < 20:
        status = "WAIT — NO CLEAR CE/PE EDGE"
    else:
        status = f"WATCH {side}"

    best = None
    if not rankings.empty:
        row = rankings.iloc[0]
        premium = _safe(row["premium"])
        ask = _safe(row["ask"], premium)
        entry = max(ask, premium * 1.01)
        stop = max(0.05, entry * 0.90)
        target1 = entry * 1.14
        target2 = entry * 1.26
        best = {
            "side": side,
            "strike": _safe(row["strike"]),
            "contract": f"{_safe(row['strike']):.0f} {side}",
            "premium": premium,
            "entry_trigger": entry,
            "stop_loss": stop,
            "target1": target1,
            "target2": target2,
            "score": _safe(row["final_score"]),
            "spread_pct": _safe(row["spread_pct"]),
            "delta": _safe(row["delta_abs"]),
            "volume": _safe(row["volume"]),
            "oi": _safe(row["oi"]),
            "oi_change": _safe(row["oi_change"]),
            "instrument_key": str(row.get("instrument_key", "")),
        }

    ce_top5 = _decorate_trade_candidates(ce_rankings, side, confirmed, confidence)
    pe_top5 = _decorate_trade_candidates(pe_rankings, side, confirmed, confidence)
    checklist = _condition_checklist(
        directional_confidence, trade_readiness, recommended_side, confidence, regime, best_row, blockers,
        ce_strength, pe_strength, strength_advantage,
    )
    passed_conditions = sum(1 for item in checklist if item["passed"])
    total_conditions = len(checklist)
    health_score = float(np.average(list(components.values()), weights=[1.2, 1.3, 1.1, 1.0, 0.9, 1.0, 0.8]))
    trade_quality = float(np.clip(health_score * 0.65 + confidence * 0.20 + (100 if confirmed else 55) * 0.15, 0, 100))

    model_probability = float(np.clip(50 + abs(score) / 6 * 30 + max(flow_strength * np.sign(score), 0) / 100 * 8, 50, 90))
    return {
        "status": status,
        "direction": direction,
        "side": side,
        "model_probability": model_probability,
        "directional_confidence": directional_confidence,
        "trade_readiness": trade_readiness,
        "recommended_side": recommended_side,
        "ce_strength": ce_strength,
        "pe_strength": pe_strength,
        "strength_advantage": strength_advantage,
        "early_move": early_move,
        "confidence": confidence,
        "confidence_detail": confidence_detail,
        "regime": regime,
        "best": best,
        "rankings": rankings.head(5),
        "ce_top5": ce_top5,
        "pe_top5": pe_top5,
        "reasons": list(dict.fromkeys(reasons)),
        "blockers": list(dict.fromkeys(blockers)),
        "confirmed": confirmed,
        "component_scores": components,
        "condition_checklist": checklist,
        "passed_conditions": passed_conditions,
        "total_conditions": total_conditions,
        "health_score": health_score,
        "trade_quality": trade_quality,
        "missing_conditions": [item["name"] for item in checklist if not item["passed"]],
        "note": "Entry, stop and targets are rule-based planning levels, not guaranteed fills or outcomes.",
    }
