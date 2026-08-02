"""Direction-neutral compression and expansion-readiness intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .decision_context import DecisionContext


@dataclass(frozen=True)
class CompressionIntelligence:
    state: str
    display_label: str
    meaning: str
    compression_score: float
    energy_stored: float
    expansion_readiness: float
    atr_compression_score: float | None
    range_compression_score: float | None
    candle_spread_compression_score: float | None
    volume_compression_score: float | None
    volatility_compression_score: float | None
    time_compression_score: float | None
    oi_build_score: float | None
    recent_atr: float | None
    baseline_atr: float | None
    atr_ratio: float | None
    recent_range: float | None
    baseline_range: float | None
    range_ratio: float | None
    recent_volume: float | None
    baseline_volume: float | None
    relative_volume: float | None
    compression_duration: int
    direction: str
    confidence: float
    evidence: tuple[str, ...]
    contradictions: tuple[str, ...]
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]


@dataclass(frozen=True)
class CompressionIntelligenceSettings:
    recent_atr_window: int = 5
    baseline_atr_window: int = 20
    recent_spread_window: int = 5
    baseline_spread_window: int = 20
    recent_range_window: int = 8
    baseline_range_window: int = 24
    recent_volume_window: int = 5
    baseline_volume_window: int = 20
    volatility_lookback: int = 20
    minimum_candle_count: int = 24
    early_threshold: float = 25.0
    moderate_threshold: float = 45.0
    high_threshold: float = 65.0
    extreme_threshold: float = 85.0
    atr_weight: float = 20.0
    range_weight: float = 20.0
    spread_weight: float = 15.0
    volume_weight: float = 10.0
    volatility_weight: float = 15.0
    time_weight: float = 15.0
    oi_weight: float = 5.0
    time_compression_minimum_duration: int = 5
    oi_build_threshold: float = 1.0
    release_threshold: float = 1.25
    expansion_threshold: float = 1.50
    readiness_release_bonus: float = 35.0
    agreement_confidence_weight: float = 70.0
    data_confidence_weight: float = 30.0
    contradiction_penalty: float = 20.0
    missing_data_confidence_ceiling: float = 45.0
    proxy_oi_confidence_ceiling: float = 55.0
    stale_data_threshold: int = 1800

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "CompressionIntelligenceSettings":
        raw = (value or {}).get("compression_intelligence", value or {})
        allowed = {item.name for item in fields(cls)}
        try:
            return cls(**{key: raw[key] for key in allowed if key in raw})
        except (TypeError, ValueError):
            return cls()


_DEFINITIONS = {
    "NO_COMPRESSION": ("No Compression", "The market is not currently storing significant directional energy."),
    "EARLY_COMPRESSION": ("Early Compression", "Price range and volatility are beginning to contract."),
    "MODERATE_COMPRESSION": ("Moderate Compression", "The market is tightening and energy may be building."),
    "HIGH_COMPRESSION": ("High Compression", "The market is trading inside a narrow, low-volatility structure."),
    "EXTREME_COMPRESSION": ("Extreme Compression", "The market is tightly compressed and may be close to a volatility expansion."),
    "RELEASING": ("Compression Releasing", "The previously compressed range is beginning to expand."),
    "EXPANDING": ("Expansion in Progress", "The market has already moved out of the compressed structure."),
    "UNAVAILABLE": ("Compression Unavailable", "Required candle or volatility data is unavailable."),
}


class CompressionIntelligenceEngine:
    """Measure supplied candles and typed context without changing a decision."""

    def __init__(self, settings: CompressionIntelligenceSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, context: DecisionContext) -> CompressionIntelligence:
        cfg = self.settings or CompressionIntelligenceSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        flags: list[str] = []
        evidence: list[str] = []
        contradictions: list[str] = []
        candles = self._candles(context.market_snapshot.historical_candles, flags)
        self._dependency_flags(context, flags)
        if candles is None or len(candles) < cfg.minimum_candle_count:
            if candles is not None:
                flags.append("CANDLES_INSUFFICIENT")
            return self._unavailable(flags, cfg)

        self._stale(candles, context, cfg, flags)
        high, low, close = candles.high, candles.low, candles.close
        previous = close.shift(1)
        true_range = pd.concat((high-low, (high-previous).abs(), (low-previous).abs()), axis=1).max(axis=1)
        recent_atr = self._mean(true_range.tail(cfg.recent_atr_window))
        baseline_atr = self._mean(true_range.tail(cfg.baseline_atr_window))
        atr_ratio, atr_score = self._ratio_score(recent_atr, baseline_atr)
        if baseline_atr == 0:
            flags.extend(("ZERO_BASELINE_ATR", "ATR_UNAVAILABLE")); atr_ratio = atr_score = None

        spreads = high-low
        recent_spread = self._mean(spreads.tail(cfg.recent_spread_window))
        baseline_spread = self._mean(spreads.tail(cfg.baseline_spread_window))
        _, spread_score = self._ratio_score(recent_spread, baseline_spread)

        recent_slice = candles.tail(cfg.recent_range_window)
        baseline_slice = candles.tail(cfg.baseline_range_window)
        recent_range = self._number(recent_slice.high.max()-recent_slice.low.min())
        baseline_range = self._number(baseline_slice.high.max()-baseline_slice.low.min())
        range_ratio, range_score = self._ratio_score(recent_range, baseline_range)
        if baseline_range == 0:
            flags.extend(("ZERO_WIDTH_RANGE", "RANGE_UNAVAILABLE")); range_ratio = range_score = None

        recent_volume = baseline_volume = relative_volume = volume_score = None
        if "volume" not in candles or candles.volume.notna().sum() < cfg.recent_volume_window:
            flags.append("VOLUME_UNAVAILABLE")
        else:
            recent_volume = self._mean(candles.volume.tail(cfg.recent_volume_window))
            baseline_volume = self._mean(candles.volume.tail(cfg.baseline_volume_window))
            relative_volume, volume_score = self._ratio_score(recent_volume, baseline_volume)

        returns = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        recent_vol = self._number(returns.tail(cfg.recent_atr_window).std())
        baseline_vol = self._number(returns.tail(cfg.volatility_lookback).std())
        _, volatility_score = self._ratio_score(recent_vol, baseline_vol)
        if volatility_score is None:
            flags.append("VOLATILITY_UNAVAILABLE")

        inside = (close.tail(cfg.baseline_range_window) >= recent_slice.low.min()) & (close.tail(cfg.baseline_range_window) <= recent_slice.high.max())
        duration = self._trailing_true(inside)
        time_score = self._clamp(duration / max(cfg.time_compression_minimum_duration * 2, 1) * 100)

        oi_score = self._oi_score(context, cfg, flags)
        components = {
            "ATR": (atr_score, cfg.atr_weight), "rolling range": (range_score, cfg.range_weight),
            "candle spread": (spread_score, cfg.spread_weight), "volume": (volume_score, cfg.volume_weight),
            "return volatility": (volatility_score, cfg.volatility_weight), "time in range": (time_score, cfg.time_weight),
            "open interest": (oi_score, cfg.oi_weight),
        }
        available = [(name, value, weight) for name, (value, weight) in components.items() if value is not None]
        score = self._clamp(sum(value*weight for _, value, weight in available) / max(sum(weight for _, _, weight in available), 1))
        for name, value, _ in available:
            (evidence if value >= 50 else contradictions).append(f"{name.title()} compression score is {value:.0f}/100.")
        strong = sum(value >= 50 for _, value, _ in available)
        weak = sum(value < 25 for _, value, _ in available)
        if strong >= 2 and weak >= 2:
            flags.append("COMPONENTS_CONFLICTED")
        if strong < 2:
            flags.append("COMPRESSION_UNCONFIRMED")

        energy = self._clamp(score*.65 + time_score*.20 + (oi_score or 0)*.15)
        current_spread = self._number(spreads.iloc[-1]) or 0.0
        prior_spread = self._mean(spreads.iloc[-(cfg.recent_spread_window+1):-1]) or 0.0
        release_ratio = current_spread / prior_spread if prior_spread > 0 else 0.0
        transition = str(getattr(context.market_location, "transition", "") or "").upper()
        boundary_release = transition in {"BREAKING_UP", "BREAKING_DOWN", "BREAKOUT_UP", "BREAKOUT_DOWN"}
        releasing = score >= cfg.moderate_threshold and (release_ratio >= cfg.release_threshold or boundary_release)
        expanding = release_ratio >= cfg.expansion_threshold and boundary_release
        readiness = self._clamp(score*.35 + energy*.30 + min(release_ratio/cfg.release_threshold, 1)*cfg.readiness_release_bonus)
        state = "EXPANDING" if expanding else "RELEASING" if releasing else self._state(score, cfg)
        if releasing:
            evidence.append("The latest range or market-location transition suggests a possible compression release.")
        direction = self._direction(context)
        agreement = 100 - (max((v for _, v, _ in available), default=0)-min((v for _, v, _ in available), default=0))
        confidence = self._clamp(agreement*cfg.agreement_confidence_weight/100 + len(available)/7*cfg.data_confidence_weight)
        if contradictions:
            confidence = self._clamp(confidence-cfg.contradiction_penalty*min(len(contradictions), 2)/2)
        critical_missing = any(f in flags for f in ("ATR_UNAVAILABLE", "RANGE_UNAVAILABLE", "OHLC_INVALID", "CANDLES_INSUFFICIENT", "STALE_DATA"))
        if critical_missing:
            confidence = min(confidence, cfg.missing_data_confidence_ceiling)
        if "OI_PROXY_ONLY" in flags:
            confidence = min(confidence, cfg.proxy_oi_confidence_ceiling)
        label, meaning = _DEFINITIONS[state]
        explanations = (
            f"What is happening: {strong} of {len(available)} available components show material contraction.",
            "What it may imply: energy may be building for a future expansion, but neither timing nor direction is guaranteed.",
            f"Directional lean is {direction.replace('_', ' ').lower()} and is informational only.",
        )
        return CompressionIntelligence(state, label, meaning, score, energy, readiness, atr_score, range_score, spread_score, volume_score, volatility_score, time_score, oi_score, recent_atr, baseline_atr, atr_ratio, recent_range, baseline_range, range_ratio, recent_volume, baseline_volume, relative_volume, duration, direction, confidence, tuple(evidence), tuple(contradictions), tuple(dict.fromkeys(flags)), explanations)

    @staticmethod
    def _candles(value: Any, flags: list[str]) -> pd.DataFrame | None:
        if value is None or not isinstance(value, pd.DataFrame) or value.empty:
            flags.append("CANDLES_MISSING"); return None
        frame = value.copy()
        frame.columns = [str(c).lower() for c in frame.columns]
        if not {"high", "low", "close"}.issubset(frame.columns):
            flags.append("OHLC_INVALID"); return None
        for column in ("high", "low", "close", "volume"):
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["high", "low", "close"])
        if frame.empty or bool((frame.high < frame.low).any()):
            flags.append("OHLC_INVALID"); return None
        return frame

    @staticmethod
    def _dependency_flags(context: DecisionContext, flags: list[str]) -> None:
        for value, flag in ((context.market_location, "MARKET_LOCATION_UNAVAILABLE"), (context.volume_structure, "VOLUME_STRUCTURE_UNAVAILABLE"), (context.positioning_intelligence, "POSITIONING_UNAVAILABLE"), (context.institutional_metrics, "INSTITUTIONAL_METRICS_UNAVAILABLE")):
            if value is None: flags.append(flag)

    def _oi_score(self, context: DecisionContext, cfg: CompressionIntelligenceSettings, flags: list[str]) -> float | None:
        summary = context.market_snapshot.option_result.get("summary", {}) if isinstance(context.market_snapshot.option_result, Mapping) else {}
        raw = summary.get("futures_oi_change") if isinstance(summary, Mapping) else None
        proxy = bool(summary.get("futures_oi_proxy")) if isinstance(summary, Mapping) else False
        value = self._number(raw)
        if proxy: flags.append("OI_PROXY_ONLY")
        if value is None:
            flags.append("OI_UNAVAILABLE"); return None
        return self._clamp(max(value, 0)/max(cfg.oi_build_threshold, 1e-9)*50)

    @staticmethod
    def _direction(context: DecisionContext) -> str:
        signals: list[str] = []
        positioning = context.positioning_intelligence
        bias = str(getattr(positioning, "overall_bias", "")).upper()
        if bias in {"BULLISH", "BEARISH"}: signals.append(bias)
        volume = str(getattr(context.volume_structure, "direction", "")).upper()
        if "BULL" in volume: signals.append("BULLISH")
        if "BEAR" in volume: signals.append("BEARISH")
        transition = str(getattr(context.market_location, "transition", "")).upper()
        if "UP" in transition: signals.append("BULLISH")
        if "DOWN" in transition: signals.append("BEARISH")
        if not signals: return "UNKNOWN"
        if len(set(signals)) > 1 or len(signals) < 2: return "UNCONFIRMED"
        return f"{signals[0]}_LEAN"

    @staticmethod
    def _state(score: float, cfg: CompressionIntelligenceSettings) -> str:
        if score >= cfg.extreme_threshold: return "EXTREME_COMPRESSION"
        if score >= cfg.high_threshold: return "HIGH_COMPRESSION"
        if score >= cfg.moderate_threshold: return "MODERATE_COMPRESSION"
        if score >= cfg.early_threshold: return "EARLY_COMPRESSION"
        return "NO_COMPRESSION"

    def _unavailable(self, flags: list[str], cfg: CompressionIntelligenceSettings) -> CompressionIntelligence:
        label, meaning = _DEFINITIONS["UNAVAILABLE"]
        return CompressionIntelligence("UNAVAILABLE", label, meaning, 0, 0, 0, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, 0, "UNKNOWN", min(10.0, cfg.missing_data_confidence_ceiling), (), (), tuple(dict.fromkeys(flags)), ("What is happening: required completed candle history is unavailable.", "What it may imply: compression cannot be assessed yet; no trading conclusion is drawn."))

    def _ratio_score(self, recent: float | None, baseline: float | None) -> tuple[float | None, float | None]:
        if recent is None or baseline is None or baseline <= 0: return None, None
        ratio = recent/baseline
        return ratio, self._clamp((1-ratio)*200)

    @staticmethod
    def _mean(series: pd.Series) -> float | None:
        return CompressionIntelligenceEngine._number(series.mean()) if len(series) else None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            result = float(value)
            return result if np.isfinite(result) else None
        except (TypeError, ValueError): return None

    @staticmethod
    def _trailing_true(series: pd.Series) -> int:
        count = 0
        for value in reversed(series.tolist()):
            if not bool(value): break
            count += 1
        return count

    @staticmethod
    def _clamp(value: float) -> float:
        return round(max(0.0, min(100.0, float(value))), 2)

    @staticmethod
    def _stale(candles: pd.DataFrame, context: DecisionContext, cfg: CompressionIntelligenceSettings, flags: list[str]) -> None:
        raw = candles["timestamp"].iloc[-1] if "timestamp" in candles else context.market_snapshot.timestamps.get("last_refresh")
        if raw in (None, ""): return
        parsed = pd.to_datetime(raw, utc=True, errors="coerce")
        if pd.isna(parsed): flags.append("INVALID_TIMESTAMP")
        elif (datetime.now(timezone.utc)-parsed.to_pydatetime()).total_seconds() > cfg.stale_data_threshold: flags.append("STALE_DATA")
