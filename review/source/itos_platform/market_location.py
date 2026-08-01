"""Typed, informational market-location and transition intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .decision_context import DecisionContext, MarketSnapshot


@dataclass(frozen=True)
class MarketLocation:
    zone: str
    location_score: float
    transition: str
    transition_strength: float
    direction: str
    range_position: float | None
    distance_to_support: float | None
    distance_to_resistance: float | None
    support_level: float | None
    resistance_level: float | None
    breakout_level: float | None
    retest_level: float | None
    confidence: float
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]


@dataclass(frozen=True)
class MarketLocationSettings:
    bottom_max: float = 15.0
    lower_max: float = 35.0
    upper_min: float = 65.0
    top_min: float = 85.0
    swing_lookback: int = 12
    rolling_range_lookback: int = 30
    minimum_candles: int = 6
    slope_lookback: int = 4
    breakout_confirmation_candles: int = 2
    breakout_atr_threshold: float = 0.10
    breakout_percentage_threshold: float = 0.001
    retest_tolerance_atr: float = 0.25
    failed_breakout_window: int = 4
    stale_data_seconds: int = 1800

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "MarketLocationSettings":
        raw = (value or {}).get("market_location", value or {})
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: raw[key] for key in allowed if key in raw})


class MarketLocationEngine:
    """Classify location without changing or creating a trade recommendation."""

    def __init__(self, settings: MarketLocationSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, value: DecisionContext | Mapping[str, Any]) -> MarketLocation:
        context = self._context(value)
        settings = self.settings or MarketLocationSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        snapshot = context.market_snapshot
        candles, error = self._candles(snapshot.historical_candles)
        flags: list[str] = []
        if error:
            flags.append(error)
            return self._unknown(flags)
        assert candles is not None
        if len(candles) < settings.minimum_candles:
            flags.append("CANDLES_INSUFFICIENT")
            return self._unknown(flags)

        price = float(candles["close"].iloc[-1])
        intelligence = snapshot.intelligence if isinstance(snapshot.intelligence, Mapping) else {}
        price_data = intelligence.get("price", {})
        price_data = price_data if isinstance(price_data, Mapping) else {}
        support = self._number(intelligence.get("support", price_data.get("support")))
        resistance = self._number(intelligence.get("resistance", price_data.get("resistance")))
        summary = snapshot.option_result.get("summary", {}) if isinstance(snapshot.option_result, Mapping) else {}
        if isinstance(summary, Mapping):
            support = support if support is not None else self._number(summary.get("support"))
            resistance = resistance if resistance is not None else self._number(summary.get("resistance"))
        if support is None:
            flags.append("SUPPORT_UNAVAILABLE")
        if resistance is None:
            flags.append("RESISTANCE_UNAVAILABLE")

        # A complete validated pair wins. Otherwise confirmed-looking interior
        # swings are preferred, with the rolling extrema as deterministic fallback.
        active_low, active_high, source = support, resistance, "validated support/resistance"
        if active_low is None or active_high is None:
            window = candles.tail(settings.swing_lookback)
            lows, highs = window["low"], window["high"]
            swing_low = lows.iloc[1:-1].min() if len(window) > 2 else None
            swing_high = highs.iloc[1:-1].max() if len(window) > 2 else None
            active_low, active_high = self._number(swing_low), self._number(swing_high)
            source = "recent swing range"
        if active_low is None or active_high is None:
            window = candles.tail(settings.rolling_range_lookback)
            active_low, active_high = self._number(window["low"].min()), self._number(window["high"].max())
            source = "rolling candle range"
        if active_low is None or active_high is None:
            flags.append("ACTIVE_RANGE_UNAVAILABLE")
            return self._unknown(flags)
        if active_high <= active_low:
            flags.append("ZERO_WIDTH_RANGE")
            return self._unknown(flags, support, resistance)

        atr = self._number(price_data.get("atr"))
        if atr is None or atr <= 0:
            previous = candles["close"].shift()
            tr = pd.concat([(candles.high-candles.low), (candles.high-previous).abs(), (candles.low-previous).abs()], axis=1).max(axis=1)
            atr = self._number(tr.tail(14).mean())
            flags.append("ATR_UNAVAILABLE")
        atr = atr or 0.0
        self._stale_flag(candles, snapshot, settings, flags)
        position = max(0.0, min((price-active_low)/(active_high-active_low), 1.0))
        score = position * 100.0
        zone = self._zone(score, settings)
        transition, direction, strength, level = self._transition(
            candles, active_low, active_high, atr, settings
        )
        if transition in {"BREAKING_UP", "BREAKING_DOWN"}:
            zone = "BREAKOUT_ZONE"
        elif transition in {"RETESTING_UP", "RETESTING_DOWN"}:
            zone = "RETEST_ZONE"
        if transition == "STABLE":
            flags.append("TRANSITION_UNCONFIRMED")
        confidence = max(15.0, 90.0 - len(flags)*10.0)
        metric_support = support if support is not None else active_low
        metric_resistance = resistance if resistance is not None else active_high
        return MarketLocation(
            zone, round(score, 4), transition, round(strength, 4), direction,
            round(position, 6), round(price-metric_support, 6),
            round(metric_resistance-price, 6),
            metric_support, metric_resistance,
            level if transition in {"BREAKING_UP", "BREAKING_DOWN", "FAILED_BREAKOUT", "FAILED_BREAKDOWN"} else None,
            level if transition in {"RETESTING_UP", "RETESTING_DOWN"} else None,
            confidence, tuple(dict.fromkeys(flags)),
            (f"Active range {active_low:.2f}–{active_high:.2f} selected from {source}.",
             f"Price {price:.2f} is at {score:.1f}% of the active range.",
             f"Transition is {transition}; this result is informational only."),
        )

    @staticmethod
    def _context(value: DecisionContext | Mapping[str, Any]) -> DecisionContext:
        if isinstance(value, DecisionContext):
            return value
        snapshot = MarketSnapshot.from_legacy(value)
        return DecisionContext(
            market_snapshot=snapshot,
            recommendation=value.get("recommendation") or {},
            engine_results=value.get("engine_results") or {},
            configuration=value.get("configuration") or {},
            runtime_configuration=value.get("runtime_configuration") or {},
        )

    @staticmethod
    def _candles(raw: Any) -> tuple[pd.DataFrame | None, str | None]:
        if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
            return None, "CANDLES_MISSING"
        try:
            frame = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        except (TypeError, ValueError):
            return None, "OHLC_INVALID"
        required = ["open", "high", "low", "close"]
        if any(column not in frame for column in required):
            return None, "OHLC_INVALID"
        numeric = frame[required].apply(pd.to_numeric, errors="coerce")
        if numeric.isna().any().any():
            return None, "OHLC_INVALID"
        frame = frame.copy()
        frame[required] = numeric
        return frame, None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
            return number if pd.notna(number) else None
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _zone(score: float, s: MarketLocationSettings) -> str:
        if score <= s.bottom_max: return "BOTTOM"
        if score <= s.lower_max: return "LOWER_RANGE"
        if score < s.upper_min: return "MIDDLE"
        if score < s.top_min: return "UPPER_RANGE"
        return "TOP"

    @staticmethod
    def _transition(c: pd.DataFrame, low: float, high: float, atr: float, s: MarketLocationSettings) -> tuple[str, str, float, float | None]:
        closes = c.close.astype(float)
        current = float(closes.iloc[-1])
        threshold = max(atr*s.breakout_atr_threshold, current*s.breakout_percentage_threshold)
        window = closes.tail(s.failed_breakout_window + 1)
        earlier = window.iloc[:-1]
        if (earlier > high + threshold).any() and current <= high:
            return "FAILED_BREAKOUT", "BEARISH", min(100.0, abs(current-high)/max(atr, 1e-9)*50), high
        if (earlier < low - threshold).any() and current >= low:
            return "FAILED_BREAKDOWN", "BULLISH", min(100.0, abs(current-low)/max(atr, 1e-9)*50), low
        tolerance = max(atr*s.retest_tolerance_atr, current*s.breakout_percentage_threshold)
        if (earlier > high + threshold).any() and current >= high and current-high <= tolerance:
            return "RETESTING_UP", "BULLISH", 70.0, high
        if (earlier < low - threshold).any() and current <= low and low-current <= tolerance:
            return "RETESTING_DOWN", "BEARISH", 70.0, low
        confirm = closes.tail(s.breakout_confirmation_candles)
        if len(confirm) == s.breakout_confirmation_candles and (confirm > high + threshold).all():
            return "BREAKING_UP", "BULLISH", min(100.0, (current-high)/max(atr, 1e-9)*50), high
        if len(confirm) == s.breakout_confirmation_candles and (confirm < low - threshold).all():
            return "BREAKING_DOWN", "BEARISH", min(100.0, (low-current)/max(atr, 1e-9)*50), low
        recent = closes.tail(s.slope_lookback)
        slope = float(recent.iloc[-1] - recent.iloc[0]) / max(len(recent)-1, 1)
        strength = min(100.0, abs(slope)/max(atr, 1e-9)*100)
        if slope > max(atr*.02, 1e-9): return "MOVING_UP", "BULLISH", strength, None
        if slope < -max(atr*.02, 1e-9): return "MOVING_DOWN", "BEARISH", strength, None
        return "STABLE", "NEUTRAL", strength, None

    @staticmethod
    def _stale_flag(c: pd.DataFrame, snapshot: MarketSnapshot, s: MarketLocationSettings, flags: list[str]) -> None:
        timestamp = c["timestamp"].iloc[-1] if "timestamp" in c else snapshot.timestamps.get("captured_at")
        if timestamp is None: return
        try:
            parsed = pd.Timestamp(timestamp)
            now = datetime.now(timezone.utc)
            if parsed.tzinfo is None: parsed = parsed.tz_localize("UTC")
            if (now-parsed.to_pydatetime()).total_seconds() > s.stale_data_seconds:
                flags.append("STALE_DATA")
        except (TypeError, ValueError, OverflowError):
            return

    @staticmethod
    def _unknown(flags: list[str], support: float | None = None, resistance: float | None = None) -> MarketLocation:
        return MarketLocation("UNKNOWN", 50.0, "STABLE", 0.0, "UNKNOWN", None, None, None,
                              support, resistance, None, None, 5.0, tuple(dict.fromkeys(flags)),
                              ("Market location is unavailable; neutral display score is not directional evidence.",))
