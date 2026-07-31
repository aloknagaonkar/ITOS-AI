from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class WindowChange:
    minutes: int
    actual_minutes: float
    spot_change: float
    spot_change_pct: float
    pcr_change: float
    max_pain_change: float
    call_oi_change: float
    put_oi_change: float
    call_premium_change: float
    put_premium_change: float
    strength: float
    label: str


def _nearest_prior(history: pd.DataFrame, minutes: int) -> pd.Series | None:
    if len(history) < 2:
        return None
    latest_time = history.iloc[-1]["captured_at"]
    target = latest_time - pd.Timedelta(minutes=minutes)
    prior = history[history["captured_at"] <= target]
    if not prior.empty:
        return prior.iloc[-1]
    return history.iloc[0]


def _deduplicate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a frame with unique column labels, preserving the first occurrence."""
    if frame.columns.is_unique:
        return frame
    return frame.loc[:, ~frame.columns.duplicated()].copy()


def _premium_totals(strike_history: pd.DataFrame, snapshot_id: int) -> tuple[float, float]:
    strike_history = _deduplicate_columns(strike_history)
    rows = strike_history.loc[strike_history["snapshot_id"].eq(snapshot_id)]
    if rows.empty:
        return 0.0, 0.0
    return float(rows["call_ltp"].sum()), float(rows["put_ltp"].sum())


def classify_flow(
    spot_change: float,
    call_oi_change: float,
    put_oi_change: float,
    call_premium_change: float,
    put_premium_change: float,
) -> tuple[str, float]:
    scale = max(abs(call_oi_change) + abs(put_oi_change), 1.0)
    oi_bias = (put_oi_change - call_oi_change) / scale
    premium_scale = max(abs(call_premium_change) + abs(put_premium_change), 1.0)
    premium_bias = (call_premium_change - put_premium_change) / premium_scale
    price_bias = float(np.sign(spot_change))
    strength = float(np.clip((oi_bias * 0.5 + premium_bias * 0.3 + price_bias * 0.2) * 100, -100, 100))

    if strength >= 55:
        return "Strong bullish institutional flow", strength
    if strength >= 20:
        return "Bullish institutional flow", strength
    if strength <= -55:
        return "Strong bearish institutional flow", strength
    if strength <= -20:
        return "Bearish institutional flow", strength
    return "Balanced / mixed institutional flow", strength


def build_window_changes(history: pd.DataFrame, strike_history: pd.DataFrame) -> list[WindowChange]:
    history = _deduplicate_columns(history)
    strike_history = _deduplicate_columns(strike_history)
    if history.empty:
        return []
    latest = history.iloc[-1]
    latest_call_premium, latest_put_premium = _premium_totals(
        strike_history, int(latest["snapshot_id"])
    )
    windows: list[WindowChange] = []
    for minutes in (5, 15, 30, 60):
        prior = _nearest_prior(history, minutes)
        if prior is None or int(prior["snapshot_id"]) == int(latest["snapshot_id"]):
            continue
        prior_call_premium, prior_put_premium = _premium_totals(
            strike_history, int(prior["snapshot_id"])
        )
        spot_change = float(latest["spot"] - prior["spot"])
        label, strength = classify_flow(
            spot_change,
            float(latest["call_oi"] - prior["call_oi"]),
            float(latest["put_oi"] - prior["put_oi"]),
            latest_call_premium - prior_call_premium,
            latest_put_premium - prior_put_premium,
        )
        actual_minutes = (latest["captured_at"] - prior["captured_at"]).total_seconds() / 60
        windows.append(
            WindowChange(
                minutes=minutes,
                actual_minutes=actual_minutes,
                spot_change=spot_change,
                spot_change_pct=spot_change / max(float(prior["spot"]), 1.0) * 100,
                pcr_change=float(latest["pcr_oi"] - prior["pcr_oi"]),
                max_pain_change=float(latest["max_pain"] - prior["max_pain"]),
                call_oi_change=float(latest["call_oi"] - prior["call_oi"]),
                put_oi_change=float(latest["put_oi"] - prior["put_oi"]),
                call_premium_change=latest_call_premium - prior_call_premium,
                put_premium_change=latest_put_premium - prior_put_premium,
                strength=strength,
                label=label,
            )
        )
    return windows


def detect_strike_flows(strike_history: pd.DataFrame, minutes: int = 15) -> pd.DataFrame:
    strike_history = _deduplicate_columns(strike_history)
    if strike_history.empty or strike_history["snapshot_id"].nunique() < 2:
        return pd.DataFrame()
    latest_time = strike_history["captured_at"].max()
    latest_id = int(
        strike_history.loc[strike_history["captured_at"] == latest_time, "snapshot_id"].iloc[0]
    )
    target = latest_time - pd.Timedelta(minutes=minutes)
    prior_candidates = strike_history[strike_history["captured_at"] <= target]
    if prior_candidates.empty:
        prior_time = strike_history["captured_at"].min()
    else:
        prior_time = prior_candidates["captured_at"].max()
    prior_id = int(
        strike_history.loc[strike_history["captured_at"] == prior_time, "snapshot_id"].iloc[0]
    )
    if latest_id == prior_id:
        return pd.DataFrame()

    latest = strike_history[strike_history["snapshot_id"] == latest_id].set_index("strike")
    prior = strike_history[strike_history["snapshot_id"] == prior_id].set_index("strike")
    shared = latest.index.intersection(prior.index)
    rows: list[dict[str, Any]] = []
    for strike in shared:
        now = latest.loc[strike]
        before = prior.loc[strike]
        ce_oi = float(now["call_oi"] - before["call_oi"])
        pe_oi = float(now["put_oi"] - before["put_oi"])
        ce_premium = float(now["call_ltp"] - before["call_ltp"])
        pe_premium = float(now["put_ltp"] - before["put_ltp"])

        ce_activity = _option_activity(ce_premium, ce_oi, "CE")
        pe_activity = _option_activity(pe_premium, pe_oi, "PE")
        magnitude = abs(ce_oi) + abs(pe_oi)
        rows.append(
            {
                "strike": float(strike),
                "spot": float(now["spot"]),
                "ce_oi_flow": ce_oi,
                "pe_oi_flow": pe_oi,
                "ce_premium_flow": ce_premium,
                "pe_premium_flow": pe_premium,
                "ce_activity": ce_activity,
                "pe_activity": pe_activity,
                "net_oi_flow": pe_oi - ce_oi,
                "magnitude": magnitude,
            }
        )
    return pd.DataFrame(rows).sort_values("magnitude", ascending=False).reset_index(drop=True)


def _option_activity(premium_change: float, oi_change: float, side: str) -> str:
    if premium_change > 0 and oi_change > 0:
        return f"{side} long buildup"
    if premium_change < 0 and oi_change > 0:
        return f"{side} fresh writing"
    if premium_change > 0 and oi_change < 0:
        return f"{side} short covering"
    if premium_change < 0 and oi_change < 0:
        return f"{side} long unwinding"
    return f"{side} neutral"


def market_narrative(
    history: pd.DataFrame,
    windows: list[WindowChange],
    strike_flows: pd.DataFrame,
) -> list[str]:
    if history.empty:
        return ["No stored market snapshot is available yet."]
    if len(history) < 2:
        return [
            "The first snapshot has been stored.",
            "Keep auto-refresh enabled for at least 15 minutes to unlock flow comparisons.",
        ]

    latest = history.iloc[-1]
    lines = [
        f"The latest stored market state is {latest['state'].lower()} with {latest['confidence']:.0f}% model confidence."
    ]
    if windows:
        primary = next((item for item in windows if item.minutes == 15), windows[0])
        lines.append(
            f"Over approximately {primary.actual_minutes:.0f} minutes, the engine detected {primary.label.lower()} "
            f"with a flow-strength score of {primary.strength:+.0f}."
        )
        lines.append(
            f"Spot changed {primary.spot_change:+.2f} points while PCR changed {primary.pcr_change:+.2f}."
        )
        if primary.put_oi_change > primary.call_oi_change:
            lines.append("Put-side OI expanded faster than call-side OI during the comparison window.")
        elif primary.call_oi_change > primary.put_oi_change:
            lines.append("Call-side OI expanded faster than put-side OI during the comparison window.")
        if primary.max_pain_change:
            direction = "higher" if primary.max_pain_change > 0 else "lower"
            lines.append(f"Max pain shifted {direction} by {abs(primary.max_pain_change):.0f} points.")
        else:
            lines.append("Max pain remained unchanged during the comparison window.")

    if not strike_flows.empty:
        strongest = strike_flows.iloc[0]
        lines.append(
            f"The strongest recent strike activity is around {strongest['strike']:.0f}: "
            f"{strongest['ce_activity']} and {strongest['pe_activity']}."
        )
    return lines


def institutional_summary(history: pd.DataFrame, strike_history: pd.DataFrame) -> dict[str, Any]:
    windows = build_window_changes(history, strike_history)
    flows = detect_strike_flows(strike_history, minutes=15)
    narrative = market_narrative(history, windows, flows)
    primary = next((window for window in windows if window.minutes == 15), windows[0] if windows else None)
    return {
        "windows": windows,
        "strike_flows": flows,
        "narrative": narrative,
        "primary_label": primary.label if primary else "Building history",
        "primary_strength": primary.strength if primary else 0.0,
    }
