from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate_max_pain(df: pd.DataFrame) -> float:
    strikes = df["strike"].to_numpy(dtype=float)
    call_oi = df["call_oi"].to_numpy(dtype=float)
    put_oi = df["put_oi"].to_numpy(dtype=float)
    pains = []
    for settlement in strikes:
        call_pain = (np.maximum(settlement - strikes, 0) * call_oi).sum()
        put_pain = (np.maximum(strikes - settlement, 0) * put_oi).sum()
        pains.append(float(call_pain + put_pain))
    return float(strikes[int(np.argmin(pains))])


def classify_buildup(price_change: float, oi_change: float) -> str:
    if price_change > 0 and oi_change > 0:
        return "Long buildup"
    if price_change < 0 and oi_change > 0:
        return "Short buildup / writing"
    if price_change > 0 and oi_change < 0:
        return "Short covering"
    if price_change < 0 and oi_change < 0:
        return "Long unwinding"
    return "Neutral"


def analyse_market(df: pd.DataFrame, strikes_each_side: int = 8) -> dict[str, Any]:
    if df.empty:
        raise ValueError("Option chain is empty.")

    non_zero_spot = df["spot"].replace(0, np.nan).dropna()
    if non_zero_spot.empty:
        raise ValueError("Underlying spot price is missing from the option-chain response.")

    spot = float(non_zero_spot.iloc[0])
    atm_index = int((df["strike"] - spot).abs().idxmin())
    atm = float(df.loc[atm_index, "strike"])
    start = max(0, atm_index - strikes_each_side)
    end = min(len(df), atm_index + strikes_each_side + 1)
    near = df.iloc[start:end].copy()

    near["call_activity"] = near.apply(
        lambda r: classify_buildup(r["call_price_change"], r["call_oi_change"]), axis=1
    )
    near["put_activity"] = near.apply(
        lambda r: classify_buildup(r["put_price_change"], r["put_oi_change"]), axis=1
    )

    call_oi = float(near["call_oi"].sum())
    put_oi = float(near["put_oi"].sum())
    call_volume = float(near["call_volume"].sum())
    put_volume = float(near["put_volume"].sum())
    pcr_oi = put_oi / call_oi if call_oi else 0.0
    pcr_volume = put_volume / call_volume if call_volume else 0.0
    call_change = float(near["call_oi_change"].sum())
    put_change = float(near["put_oi_change"].sum())

    below = near[near["strike"] <= spot]
    above = near[near["strike"] >= spot]
    support_pool = below if not below.empty else near
    resistance_pool = above if not above.empty else near
    support = float(support_pool.loc[support_pool["put_oi"].idxmax(), "strike"])
    resistance = float(resistance_pool.loc[resistance_pool["call_oi"].idxmax(), "strike"])

    top_call_writing = near.nlargest(3, "call_oi_change")[["strike", "call_oi_change"]]
    top_put_writing = near.nlargest(3, "put_oi_change")[["strike", "put_oi_change"]]

    atm_row = near.loc[near["strike"].sub(atm).abs().idxmin()]
    atm_iv = float((atm_row["call_iv"] + atm_row["put_iv"]) / 2)
    iv_skew = float(atm_row["put_iv"] - atm_row["call_iv"])

    score = 0.0
    reasons: list[str] = []

    if 1.0 <= pcr_oi <= 1.5:
        score += 1.5
        reasons.append("OI PCR shows constructive put-side support")
    elif pcr_oi > 1.5:
        score += 0.5
        reasons.append("OI PCR is high; support exists but crowding risk is elevated")
    elif pcr_oi < 0.8:
        score -= 1.5
        reasons.append("OI PCR shows relatively heavy call-side positioning")
    else:
        reasons.append("OI PCR is broadly neutral")

    if pcr_volume > 1.15:
        score += 0.6
        reasons.append("Put volume is leading call volume")
    elif pcr_volume < 0.85:
        score -= 0.6
        reasons.append("Call volume is leading put volume")

    total_change = abs(call_change) + abs(put_change)
    if total_change:
        imbalance = (put_change - call_change) / total_change
        score += 3.0 * float(np.clip(imbalance, -1, 1))
        if imbalance > 0.15:
            reasons.append("Put OI addition is stronger than call OI addition")
        elif imbalance < -0.15:
            reasons.append("Call OI addition is stronger than put OI addition")
        else:
            reasons.append("Call and put OI changes are balanced")

    if iv_skew > 2:
        score += 0.4
        reasons.append("ATM put IV is above call IV")
    elif iv_skew < -2:
        score -= 0.4
        reasons.append("ATM call IV is above put IV")

    score = float(np.clip(score, -7, 7))
    confidence = min(95.0, 50.0 + abs(score) / 7.0 * 45.0)
    if score >= 2:
        bias = "Bullish"
        strength = "Strong" if score >= 4 else "Moderate"
        setup = "Watch for a CE setup only after price confirmation"
    elif score <= -2:
        bias = "Bearish"
        strength = "Strong" if score <= -4 else "Moderate"
        setup = "Watch for a PE setup only after price confirmation"
    else:
        bias = "Neutral"
        strength = "Weak"
        setup = "No directional setup; wait for price and OI confirmation"

    activity_counts = {
        "call_writing": int((near["call_activity"] == "Short buildup / writing").sum()),
        "put_writing": int((near["put_activity"] == "Short buildup / writing").sum()),
        "call_short_covering": int((near["call_activity"] == "Short covering").sum()),
        "put_short_covering": int((near["put_activity"] == "Short covering").sum()),
    }

    return {
        "chain": near,
        "top_call_writing": top_call_writing,
        "top_put_writing": top_put_writing,
        "summary": {
            "spot": spot,
            "atm": atm,
            "pcr_oi": pcr_oi,
            "pcr_volume": pcr_volume,
            "support": support,
            "resistance": resistance,
            "max_pain": calculate_max_pain(near),
            "call_oi_change": call_change,
            "put_oi_change": put_change,
            "atm_iv": atm_iv,
            "iv_skew": iv_skew,
            "score": score,
            "confidence": confidence,
            "bias": bias,
            "strength": strength,
            "setup": setup,
            "explanation": "; ".join(reasons[:5]) + ".",
            "reasons": reasons,
            **activity_counts,
        },
    }
