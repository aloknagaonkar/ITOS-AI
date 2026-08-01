"""Location-aware, informational price and volume intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .decision_context import DecisionContext


@dataclass(frozen=True)
class VolumeStructure:
    price_direction: str
    price_strength: float
    price_change_percent: float | None
    price_slope: float | None
    volume_direction: str
    volume_strength: float
    volume_change_percent: float | None
    relative_volume: float | None
    volume_confirmation: str
    effort_result_state: str
    interpretation: str
    direction: str
    accumulation_score: float
    distribution_score: float
    absorption_score: float
    exhaustion_score: float
    confidence: float
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]


@dataclass(frozen=True)
class VolumeStructureSettings:
    minimum_candles: int = 8
    price_slope_lookback: int = 6
    price_flat_threshold: float = 0.0005
    price_slope_weight: float = 35.0
    price_change_weight: float = 35.0
    price_consistency_weight: float = 30.0
    volume_trend_lookback: int = 5
    relative_volume_baseline: int = 20
    volume_flat_threshold: float = 0.08
    confirmation_threshold: float = 0.05
    high_effort_ratio: float = 1.20
    large_result_percent: float = 0.60
    absorption_minimum_volume: float = 1.25
    absorption_maximum_price_result: float = 0.35
    exhaustion_lookback: int = 5
    accumulation_location_weight: float = 40.0
    accumulation_participation_weight: float = 40.0
    accumulation_absorption_weight: float = 20.0
    distribution_location_weight: float = 40.0
    distribution_participation_weight: float = 40.0
    distribution_absorption_weight: float = 20.0
    stale_data_seconds: int = 1800

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "VolumeStructureSettings":
        raw = (value or {}).get("volume_structure", value or {})
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: raw[key] for key in allowed if key in raw})


class VolumeStructureEngine:
    """Measure price/volume facts, then interpret them at a mandatory location."""

    def __init__(self, settings: VolumeStructureSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, context: DecisionContext) -> VolumeStructure:
        settings = self.settings or VolumeStructureSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        location = context.market_location
        if location is None or location.zone == "UNKNOWN":
            return self._unknown(("MARKET_LOCATION_UNAVAILABLE",))
        raw = context.market_snapshot.historical_candles
        if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
            return self._unknown(("CANDLES_MISSING",))
        try:
            candles = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        except (TypeError, ValueError):
            return self._unknown(("OHLC_INVALID",))
        required = ("open", "high", "low", "close")
        if any(name not in candles for name in required):
            return self._unknown(("OHLC_INVALID",))
        numeric = candles[list(required)].apply(pd.to_numeric, errors="coerce")
        if numeric.isna().any().any() or (numeric.high < numeric.low).any():
            return self._unknown(("OHLC_INVALID",))
        if len(candles) < settings.minimum_candles:
            return self._unknown(("CANDLES_INSUFFICIENT",))
        candles[list(required)] = numeric
        if "volume" not in candles:
            return self._unknown(("VOLUME_MISSING",))
        volume = pd.to_numeric(candles.volume, errors="coerce")
        if volume.isna().any() or (volume <= 0).any():
            return self._unknown(("VOLUME_INVALID",))
        candles["volume"] = volume

        closes = candles.close.astype(float)
        recent = closes.tail(settings.price_slope_lookback)
        slope = (float(recent.iloc[-1]) - float(recent.iloc[0])) / max(len(recent)-1, 1)
        slope_ratio = slope / max(abs(float(recent.iloc[0])), 1e-9)
        change = (float(recent.iloc[-1]) / float(recent.iloc[0]) - 1.0) * 100.0
        threshold = settings.price_flat_threshold
        price_direction = "RISING" if slope_ratio > threshold else "FALLING" if slope_ratio < -threshold else "FLAT"
        changes = recent.diff().dropna()
        consistency = float((changes > 0).mean() if price_direction == "RISING" else (changes < 0).mean() if price_direction == "FALLING" else (changes.abs() <= recent.mean()*threshold).mean())
        price_strength = self._clamp(
            min(abs(slope_ratio)/max(threshold, 1e-9), 1)*settings.price_slope_weight
            + min(abs(change)/max(settings.large_result_percent, 1e-9), 1)*settings.price_change_weight
            + consistency*settings.price_consistency_weight
        )

        volume_recent = volume.tail(settings.volume_trend_lookback)
        baseline_slice = volume.iloc[-(settings.relative_volume_baseline + settings.volume_trend_lookback):-settings.volume_trend_lookback]
        flags: list[str] = []
        if baseline_slice.empty:
            baseline_slice = volume.iloc[:-settings.volume_trend_lookback]
        if baseline_slice.empty or float(baseline_slice.mean()) <= 0:
            flags.append("VOLUME_BASELINE_UNAVAILABLE")
            baseline = float(volume.mean())
        else:
            baseline = float(baseline_slice.mean())
        relative = float(volume_recent.mean()) / max(baseline, 1e-9)
        volume_change = (float(volume_recent.iloc[-1])/float(volume_recent.iloc[0])-1)*100
        volume_ratio_change = volume_change / 100.0
        vf = settings.volume_flat_threshold
        volume_direction = "RISING" if volume_ratio_change > vf or relative > 1+vf else "FALLING" if volume_ratio_change < -vf and relative < 1+vf else "FLAT"
        volume_strength = self._clamp(max(abs(volume_ratio_change), abs(relative-1))*100)
        if volume_direction == "RISING" and price_direction in {"RISING", "FALLING"}:
            confirmation = "CONFIRMED"
        elif volume_direction == "FALLING" and price_direction in {"RISING", "FALLING"}:
            confirmation = "DIVERGING"
        else:
            confirmation = "NEUTRAL"

        result = abs(change)
        high_effort = relative >= settings.high_effort_ratio
        large_result = result >= settings.large_result_percent
        if high_effort and result <= settings.absorption_maximum_price_result:
            effort = "ABSORPTION"
        elif high_effort and large_result:
            effort = "STRONG_DEMAND" if price_direction == "RISING" else "STRONG_SUPPLY" if price_direction == "FALLING" else "ABSORPTION"
        elif volume_direction == "FALLING" and price_direction != "FLAT":
            effort = "EXHAUSTION" if not large_result else ("WEAK_DEMAND" if price_direction == "RISING" else "WEAK_SUPPLY")
        else:
            effort = "BALANCED"
        interpretation, direction = self._interpret(location.zone, location.transition, price_direction, volume_direction, effort)
        absorption = self._clamp((relative/settings.absorption_minimum_volume)*60 + max(0, settings.absorption_maximum_price_result-result)*80) if effort == "ABSORPTION" else 0.0
        exhaustion = self._clamp((1-min(relative, 1))*60 + (40 if effort == "EXHAUSTION" else 0))
        low_location = location.zone in {"BOTTOM", "LOWER_RANGE"}
        high_location = location.zone in {"TOP", "UPPER_RANGE"}
        accumulation = self._clamp((settings.accumulation_location_weight if low_location else 0) + (settings.accumulation_participation_weight if price_direction == volume_direction == "RISING" else 0) + absorption*settings.accumulation_absorption_weight/100)
        distribution = self._clamp((settings.distribution_location_weight if high_location else 0) + (settings.distribution_participation_weight if price_direction == "FALLING" and volume_direction == "RISING" else 0) + absorption*settings.distribution_absorption_weight/100)
        if location.transition in {"FAILED_BREAKOUT", "FAILED_BREAKDOWN"}:
            flags.append("CONFLICTING_STRUCTURE")
        self._stale(candles, context, settings, flags)
        confidence = self._clamp(85 - len(flags)*12 - (25 if location.transition in {"FAILED_BREAKOUT", "FAILED_BREAKDOWN"} else 0))
        return VolumeStructure(price_direction, round(price_strength, 4), round(change, 6), round(slope, 6), volume_direction, round(volume_strength, 4), round(volume_change, 6), round(relative, 6), confirmation, effort, interpretation, direction, round(accumulation, 4), round(distribution, 4), round(absorption, 4), round(exhaustion, 4), confidence, tuple(flags), (f"Price is {price_direction.lower()} across {len(recent)} closes ({change:.2f}%).", f"Recent volume is {relative:.2f}x its baseline and {volume_direction.lower()}.", f"At {location.zone}, effort versus result is {effort}; interpretation is informational only."))

    @staticmethod
    def _interpret(zone: str, transition: str, price: str, volume: str, effort: str) -> tuple[str, str]:
        if transition in {"FAILED_BREAKOUT", "FAILED_BREAKDOWN"}: return "NEUTRAL", "NEUTRAL"
        if effort == "ABSORPTION": return "ABSORPTION_DEVELOPING", "BULLISH" if zone in {"BOTTOM","LOWER_RANGE"} else "BEARISH" if zone in {"TOP","UPPER_RANGE"} else "NEUTRAL"
        if zone == "RETEST_ZONE" and transition == "RETESTING_UP" and volume in {"RISING","FALLING"}: return "HEALTHY_PULLBACK", "BULLISH"
        if zone == "BREAKOUT_ZONE" and price == "RISING": return ("BULLISH_EXPANSION", "BULLISH") if volume == "RISING" else ("WEAK_RALLY", "NEUTRAL")
        if zone in {"BOTTOM","LOWER_RANGE"}:
            if price == "RISING" and volume == "RISING": return "POSSIBLE_ACCUMULATION", "BULLISH"
            if price == "RISING" and volume == "FALLING": return "WEAK_RALLY", "NEUTRAL"
            if price == "FALLING" and volume == "RISING": return "SELLING_CLIMAX_RISK", "BEARISH"
            if price == "FALLING" and volume == "FALLING": return "WEAK_DECLINE", "NEUTRAL"
        if zone in {"TOP","UPPER_RANGE"}:
            if price == "FALLING" and volume == "RISING": return "POSSIBLE_DISTRIBUTION", "BEARISH"
            if price == "RISING" and volume == "FALLING": return "WEAK_RALLY", "NEUTRAL"
            if price == "RISING" and volume == "RISING": return "BUYING_CLIMAX_RISK", "BULLISH"
            if price == "FALLING" and volume == "FALLING": return "WEAK_DECLINE", "NEUTRAL"
        if zone == "MIDDLE":
            if price == "RISING" and volume == "RISING": return "BULLISH_EXPANSION", "BULLISH"
            if price == "FALLING" and volume == "RISING": return "BEARISH_EXPANSION", "BEARISH"
            if price == "RISING" and volume == "FALLING": return "WEAK_RALLY", "NEUTRAL"
            if price == "FALLING" and volume == "FALLING": return "WEAK_DECLINE", "NEUTRAL"
        return "NEUTRAL", "NEUTRAL"

    @staticmethod
    def _clamp(value: float) -> float: return max(0.0, min(100.0, value))

    @staticmethod
    def _stale(candles: pd.DataFrame, context: DecisionContext, settings: VolumeStructureSettings, flags: list[str]) -> None:
        stamp = candles["timestamp"].iloc[-1] if "timestamp" in candles else context.market_snapshot.timestamps.get("captured_at")
        if stamp is None: return
        try:
            parsed = pd.Timestamp(stamp)
            if parsed.tzinfo is None: parsed = parsed.tz_localize("UTC")
            if (datetime.now(timezone.utc)-parsed.to_pydatetime()).total_seconds() > settings.stale_data_seconds: flags.append("STALE_DATA")
        except (TypeError, ValueError, OverflowError): flags.append("STALE_DATA")

    @staticmethod
    def _unknown(flags: tuple[str, ...]) -> VolumeStructure:
        return VolumeStructure("UNKNOWN", 0.0, None, None, "UNKNOWN", 0.0, None, None, "UNAVAILABLE", "UNAVAILABLE", "NEUTRAL", "UNKNOWN", 0.0, 0.0, 0.0, 0.0, 5.0, flags, ("Price-volume behaviour is unavailable and cannot provide directional evidence.",))
