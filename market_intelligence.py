from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def enrich_candles(candles: pd.DataFrame) -> pd.DataFrame:
    df = candles.copy()
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()

    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    volume = df["volume"].replace(0, np.nan)
    cumulative_volume = volume.cumsum()
    df["vwap"] = (typical * volume).cumsum() / cumulative_volume
    df["vwap"] = df["vwap"].ffill().fillna(df["close"])

    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr14"] = true_range.rolling(14, min_periods=3).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=5).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi14"] = (100 - (100 / (1 + rs))).fillna(50)
    return df


def evaluate_price_action(candles: pd.DataFrame) -> dict[str, Any]:
    df = enrich_candles(candles)
    latest = df.iloc[-1]
    score = 0.0
    reasons: list[str] = []

    if latest["close"] > latest["ema9"] > latest["ema21"]:
        score += 2.0
        reasons.append("Price is above EMA 9 and EMA 21 with bullish alignment")
    elif latest["close"] < latest["ema9"] < latest["ema21"]:
        score -= 2.0
        reasons.append("Price is below EMA 9 and EMA 21 with bearish alignment")
    elif latest["ema9"] > latest["ema21"]:
        score += 0.7
        reasons.append("EMA 9 remains above EMA 21")
    elif latest["ema9"] < latest["ema21"]:
        score -= 0.7
        reasons.append("EMA 9 remains below EMA 21")

    if latest["close"] > latest["vwap"]:
        score += 1.3
        reasons.append("Spot is trading above intraday VWAP")
    else:
        score -= 1.3
        reasons.append("Spot is trading below intraday VWAP")

    lookback = df.tail(min(6, len(df)))
    momentum = float(lookback["close"].iloc[-1] - lookback["close"].iloc[0])
    atr = float(latest["atr14"]) if pd.notna(latest["atr14"]) else 0.0
    normalized_momentum = momentum / atr if atr > 0 else 0.0
    score += float(np.clip(normalized_momentum, -1.5, 1.5))
    if normalized_momentum > 0.5:
        reasons.append("Recent candle momentum is positive")
    elif normalized_momentum < -0.5:
        reasons.append("Recent candle momentum is negative")

    rsi = float(latest["rsi14"])
    if 55 <= rsi <= 70:
        score += 0.5
        reasons.append("RSI supports bullish momentum without being extreme")
    elif 30 <= rsi <= 45:
        score -= 0.5
        reasons.append("RSI supports bearish momentum without being extreme")
    elif rsi > 75:
        score -= 0.3
        reasons.append("RSI is stretched, increasing pullback risk")
    elif rsi < 25:
        score += 0.3
        reasons.append("RSI is stretched, increasing bounce risk")

    score = float(np.clip(score, -5, 5))
    return {
        "candles": df,
        "score": score,
        "close": float(latest["close"]),
        "ema9": float(latest["ema9"]),
        "ema21": float(latest["ema21"]),
        "vwap": float(latest["vwap"]),
        "atr": atr,
        "rsi": rsi,
        "reasons": reasons,
    }


def combine_intelligence(option_result: dict[str, Any], price_result: dict[str, Any]) -> dict[str, Any]:
    option_summary = option_result["summary"]
    option_score = float(option_summary["score"])
    price_score = float(price_result["score"])

    # The option chain carries slightly more weight, but price must confirm it.
    combined = float(np.clip(option_score * 0.58 + price_score * 0.42, -6, 6))
    agreement = np.sign(option_score) == np.sign(price_score) and abs(option_score) >= 1 and abs(price_score) >= 1
    conflict = np.sign(option_score) != np.sign(price_score) and abs(option_score) >= 1 and abs(price_score) >= 1

    support = float(option_summary["support"])
    resistance = float(option_summary["resistance"])
    spot = float(option_summary["spot"])
    atr = max(float(price_result["atr"]), 1.0)
    near_support = abs(spot - support) <= atr * 0.6
    near_resistance = abs(resistance - spot) <= atr * 0.6

    no_trade_reasons: list[str] = []
    if conflict:
        no_trade_reasons.append("Option-chain and price signals conflict")
    if abs(combined) < 1.35:
        no_trade_reasons.append("Combined directional edge is weak")
    if support < spot < resistance and (resistance - support) <= atr * 1.2:
        no_trade_reasons.append("Spot is compressed between nearby OI walls")

    if combined >= 4:
        state = "Strong Bullish"
    elif combined >= 1.35:
        state = "Bullish"
    elif combined <= -4:
        state = "Strong Bearish"
    elif combined <= -1.35:
        state = "Bearish"
    else:
        state = "Neutral"

    no_trade = bool(no_trade_reasons)
    confidence = 50 + min(abs(combined) / 6 * 42, 42)
    if agreement:
        confidence += 4
    if conflict:
        confidence -= 12
    confidence = float(np.clip(confidence, 35, 95))

    bullish_probability = float(np.clip(50 + combined / 6 * 45, 5, 95))
    bearish_probability = 100.0 - bullish_probability

    if no_trade:
        action = "No-trade zone — wait for price and OI alignment"
    elif combined > 0:
        action = "Watch for a CE setup after a confirmed hold above VWAP/EMA or resistance breakout"
    else:
        action = "Watch for a PE setup after a confirmed hold below VWAP/EMA or support breakdown"

    risk_flags: list[str] = []
    if near_resistance and combined > 0:
        risk_flags.append("Bullish setup is close to the call-OI resistance wall")
    if near_support and combined < 0:
        risk_flags.append("Bearish setup is close to the put-OI support wall")
    if abs(option_summary["iv_skew"]) > 4:
        risk_flags.append("ATM IV skew is elevated")
    if price_result["rsi"] > 75 or price_result["rsi"] < 25:
        risk_flags.append("Momentum is stretched")

    evidence = list(option_summary.get("reasons", []))[:4] + price_result["reasons"][:4]
    return {
        "state": state,
        "score": combined,
        "confidence": confidence,
        "bullish_probability": bullish_probability,
        "bearish_probability": bearish_probability,
        "agreement": agreement,
        "conflict": conflict,
        "no_trade": no_trade,
        "no_trade_reasons": no_trade_reasons,
        "action": action,
        "evidence": evidence,
        "risk_flags": risk_flags,
        "price": price_result,
    }
