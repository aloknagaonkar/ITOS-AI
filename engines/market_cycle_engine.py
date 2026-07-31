from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .base_engine import BaseEngine, EngineResult


def _safe(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


class MarketCycleEngine(BaseEngine):
    name = "Market Cycle"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        intelligence = market_data.get("intelligence", {})
        option_result = market_data.get("option_result", {})
        institutional = market_data.get("institutional") or {}
        price = intelligence.get("price", {})
        summary = option_result.get("summary", {})
        candles = price.get("candles", pd.DataFrame())

        if not isinstance(candles, pd.DataFrame) or len(candles) < 8:
            return EngineResult(
                engine=self.name, score=20.0, vote="WAIT",
                explanation=["Insufficient candle history for reliable market-cycle classification"],
                metadata={"phase": "Unknown", "phase_confidence": 20.0, "probabilities": {"Unknown": 100.0}, "trade_allowed": False},
            )

        c = candles.copy()
        for col in ["open", "high", "low", "close", "volume"]:
            c[col] = pd.to_numeric(c[col], errors="coerce")
        c = c.dropna(subset=["open", "high", "low", "close"]).tail(30)
        if len(c) < 8:
            return EngineResult(engine=self.name, score=20.0, vote="WAIT", explanation=["Candle data is incomplete"], metadata={"phase": "Unknown", "phase_confidence": 20.0, "probabilities": {"Unknown": 100.0}, "trade_allowed": False})

        tr = pd.concat([
            c["high"] - c["low"],
            (c["high"] - c["close"].shift()).abs(),
            (c["low"] - c["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        recent_atr = _safe(tr.tail(5).mean())
        baseline_atr = max(_safe(tr.tail(20).mean()), 1e-9)
        atr_ratio = recent_atr / baseline_atr
        body_ratio = ((c["close"] - c["open"]).abs() / (c["high"] - c["low"]).replace(0, np.nan)).fillna(0.0)
        recent_body = _safe(body_ratio.tail(5).mean())
        price_range = _safe(c["high"].tail(10).max() - c["low"].tail(10).min())
        range_ratio = price_range / max(baseline_atr * 10, 1e-9)

        volume = c["volume"].fillna(0.0)
        recent_volume = _safe(volume.tail(3).mean())
        baseline_volume = max(_safe(volume.tail(20).median()), 1.0)
        rvol = recent_volume / baseline_volume

        close = _safe(price.get("close", c["close"].iloc[-1]))
        vwap = _safe(price.get("vwap", close), close)
        ema9 = _safe(price.get("ema9", close), close)
        ema21 = _safe(price.get("ema21", close), close)
        trend_strength = abs(ema9 - ema21) / max(baseline_atr, 1e-9)
        above_vwap = close >= vwap

        score = _safe(intelligence.get("score"))
        flow = _safe(institutional.get("primary_strength"))
        call_change = _safe(summary.get("call_oi_change"))
        put_change = _safe(summary.get("put_oi_change"))
        oi_scale = max(abs(call_change) + abs(put_change), 1.0)
        bullish_oi = (put_change - call_change) / oi_scale
        bearish_oi = -bullish_oi

        last = c.iloc[-1]
        candle_range = max(_safe(last["high"] - last["low"]), 1e-9)
        upper_wick = _safe(last["high"] - max(last["open"], last["close"])) / candle_range
        lower_wick = _safe(min(last["open"], last["close"]) - last["low"]) / candle_range
        wick_extreme = max(upper_wick, lower_wick)
        close_location = (_safe(last["close"]) - _safe(last["low"])) / candle_range
        failed_break = wick_extreme >= 0.50 and recent_body < 0.55 and rvol >= 1.25

        compression = _clip((1.05 - atr_ratio) * 75 + (0.9 - range_ratio) * 35 + (1.0 - min(rvol, 1.0)) * 25 + (0.55 - recent_body) * 25)
        accumulation = _clip(35 + (18 if above_vwap else -12) + max(score, 0) * 6 + max(flow, 0) * 0.22 + bullish_oi * 22 + max(rvol - 0.8, 0) * 12 - max(trend_strength - 1.6, 0) * 8)
        distribution = _clip(35 + (18 if not above_vwap else -12) + max(-score, 0) * 6 + max(-flow, 0) * 0.22 + bearish_oi * 22 + max(rvol - 0.8, 0) * 12 - max(trend_strength - 1.6, 0) * 8)
        manipulation = _clip((55 if failed_break else 5) + wick_extreme * 25 + max(rvol - 1.2, 0) * 18 + (12 if abs(score) < 1.2 else 0))
        bullish_expansion = _clip(25 + max(score, 0) * 8 + max(flow, 0) * 0.18 + max(rvol - 1.0, 0) * 20 + trend_strength * 15 + (12 if above_vwap else -20) + bullish_oi * 15)
        bearish_expansion = _clip(25 + max(-score, 0) * 8 + max(-flow, 0) * 0.18 + max(rvol - 1.0, 0) * 20 + trend_strength * 15 + (12 if not above_vwap else -20) + bearish_oi * 15)

        raw = {
            "Compression": compression,
            "Accumulation": accumulation,
            "Manipulation": manipulation,
            "Bullish Expansion": bullish_expansion,
            "Bearish Expansion": bearish_expansion,
            "Distribution": distribution,
        }
        total = sum(max(v, 0.1) for v in raw.values())
        probabilities = {k: round(max(v, 0.1) / total * 100.0, 1) for k, v in raw.items()}
        phase = max(probabilities, key=probabilities.get)
        phase_confidence = probabilities[phase]

        if phase == "Bullish Expansion":
            vote = "CE"
        elif phase in {"Bearish Expansion", "Distribution"}:
            vote = "PE"
        else:
            vote = "WAIT"
        trade_allowed = phase in {"Bullish Expansion", "Bearish Expansion"} and manipulation < 55

        explanations = [
            f"ATR ratio is {atr_ratio:.2f} and relative volume is {rvol:.2f}×",
            f"Price is {'above' if above_vwap else 'below'} VWAP; EMA separation is {trend_strength:.2f} ATR",
            f"Institutional-flow strength is {flow:+.0f} and option bias is {bullish_oi:+.2f}",
        ]
        if failed_break:
            explanations.append("A high-volume long-wick candle indicates a possible liquidity sweep or trap")
        if phase == "Compression":
            explanations.append("Energy is building; entries remain blocked until directional expansion confirms")
        elif phase == "Accumulation":
            explanations.append("Bullish positioning is developing, but expansion has not yet confirmed")
        elif phase == "Distribution":
            explanations.append("Bearish positioning or profit distribution is increasing")
        elif "Expansion" in phase:
            explanations.append("Trend, participation and positioning support directional expansion")

        return EngineResult(
            engine=self.name,
            score=phase_confidence,
            vote=vote,
            explanation=explanations,
            metadata={
                "phase": phase,
                "phase_confidence": phase_confidence,
                "probabilities": probabilities,
                "trade_allowed": trade_allowed,
                "manipulation_score": manipulation,
                "atr_ratio": atr_ratio,
                "relative_volume": rvol,
                "direction": vote,
            },
        )
