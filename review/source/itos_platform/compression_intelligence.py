"""Calculated, decision-neutral compression and expansion intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .decision_context import DecisionContext, MarketSnapshot


@dataclass(frozen=True)
class CompressionIntelligenceSettings:
    recent_atr_window: int = 5
    baseline_atr_window: int = 20
    recent_spread_window: int = 5
    baseline_spread_window: int = 20
    recent_range_window: int = 5
    baseline_range_window: int = 20
    recent_volume_window: int = 5
    baseline_volume_window: int = 20
    volatility_window: int = 5
    minimum_candles: int = 20
    atr_weight: float = 22.0
    range_weight: float = 18.0
    spread_weight: float = 18.0
    volume_weight: float = 12.0
    volatility_weight: float = 14.0
    time_weight: float = 10.0
    oi_weight: float = 6.0
    early_threshold: float = 25.0
    moderate_threshold: float = 45.0
    high_threshold: float = 65.0
    extreme_threshold: float = 82.0
    release_threshold: float = 55.0
    expansion_threshold: float = 75.0
    stale_data_seconds: int = 1800
    missing_data_confidence_ceiling: float = 65.0
    proxy_oi_confidence_ceiling: float = 55.0

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "CompressionIntelligenceSettings":
        raw = (value or {}).get("compression_intelligence", value or {})
        allowed = {item.name for item in fields(cls)}
        try:
            return cls(**{key: raw[key] for key in allowed if key in raw})
        except (TypeError, ValueError):
            return cls()


@dataclass(frozen=True)
class CompressionIntelligence:
    state: str = "UNAVAILABLE"
    display_label: str = "Compression Unavailable"
    meaning: str = "Required candle or volatility data is unavailable."
    compression_score: float = 0.0
    energy_stored: float = 0.0
    expansion_readiness: float = 0.0
    atr_compression_score: float | None = None
    range_compression_score: float | None = None
    candle_spread_compression_score: float | None = None
    volume_compression_score: float | None = None
    volatility_compression_score: float | None = None
    time_compression_score: float | None = None
    oi_build_score: float | None = None
    recent_atr: float | None = None
    baseline_atr: float | None = None
    atr_ratio: float | None = None
    recent_range: float | None = None
    baseline_range: float | None = None
    range_ratio: float | None = None
    recent_volume: float | None = None
    baseline_volume: float | None = None
    relative_volume: float | None = None
    compression_duration: int = 0
    direction: str = "UNKNOWN"
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ("COMPRESSION_UNCONFIRMED",)
    explanations: tuple[str, ...] = ()


class CompressionIntelligenceEngine:
    """Measure completed candle compression without repositories or recommendations."""

    ALIASES = {
        "timestamp": ("timestamp", "time", "datetime", "date", "ts"),
        "open": ("open", "o", "Open"), "high": ("high", "h", "High"),
        "low": ("low", "l", "Low"), "close": ("close", "c", "Close", "ltp"),
        "volume": ("volume", "v", "Volume", "vol"),
    }

    def __init__(self, settings: CompressionIntelligenceSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, value: DecisionContext | Mapping[str, Any]) -> CompressionIntelligence:
        try:
            context = self._context(value)
            cfg = self.settings or CompressionIntelligenceSettings.from_mapping(
                context.configuration or context.runtime_configuration
            )
            candles, flags, malformed = self._candles(
                context.market_snapshot.historical_candles,
                context.market_snapshot.timestamps,
            )
            if candles is None:
                return self._unavailable(flags)
            if len(candles) < cfg.minimum_candles:
                return self._unavailable((*flags, "CANDLES_INSUFFICIENT"))
            return self._calculate(context, candles, cfg, list(flags), malformed)
        except Exception:
            # This analytical boundary must safely degrade for provider-native input.
            return self._unavailable(("OHLC_INVALID", "COMPRESSION_UNCONFIRMED"))

    def _calculate(self, context, c, cfg, flags, malformed):
        evidence: list[str] = []
        contradictions: list[str] = []
        previous = c.close.shift(1)
        tr = pd.concat((c.high-c.low, (c.high-previous).abs(), (c.low-previous).abs()), axis=1).max(axis=1)
        recent_atr = self._mean(tr.tail(cfg.recent_atr_window))
        baseline_atr = self._mean(tr.tail(cfg.baseline_atr_window))
        atr_ratio = self._ratio(recent_atr, baseline_atr)
        if baseline_atr == 0:
            flags.extend(("ZERO_BASELINE_ATR", "ATR_UNAVAILABLE")); atr_score = None
        elif atr_ratio is None:
            flags.append("ATR_UNAVAILABLE"); atr_score = None
        else:
            atr_score = self._ratio_score(atr_ratio)
            (evidence if atr_ratio < 1 else contradictions).append(f"Recent ATR is {atr_ratio:.2f}× its baseline.")

        spreads = c.high-c.low
        recent_spread = self._median(spreads.tail(cfg.recent_spread_window))
        baseline_spread = self._median(spreads.tail(cfg.baseline_spread_window))
        spread_ratio = self._ratio(recent_spread, baseline_spread)
        spread_score = self._ratio_score(spread_ratio) if spread_ratio is not None else None

        recent_slice = c.tail(cfg.recent_range_window)
        baseline_slice = c.tail(cfg.baseline_range_window)
        recent_range = float(recent_slice.high.max()-recent_slice.low.min())
        baseline_range = float(baseline_slice.high.max()-baseline_slice.low.min())
        range_ratio = self._ratio(recent_range, baseline_range)
        if baseline_range <= 0 or recent_range <= 0:
            flags.extend(("ZERO_WIDTH_RANGE", "RANGE_UNAVAILABLE")); range_score = None
        else:
            # Window-width adjustment makes like-for-like multi-candle containment explicit.
            adjusted_range_ratio = range_ratio * cfg.baseline_range_window / cfg.recent_range_window
            range_score = self._ratio_score(adjusted_range_ratio)

        recent_volume = baseline_volume = relative_volume = volume_score = None
        if "volume" not in c or c.volume.dropna().empty:
            flags.append("VOLUME_UNAVAILABLE")
        else:
            recent_volume = self._mean(c.volume.tail(cfg.recent_volume_window))
            baseline_volume = self._mean(c.volume.tail(cfg.baseline_volume_window))
            relative_volume = self._ratio(recent_volume, baseline_volume)
            volume_score = self._ratio_score(relative_volume) if relative_volume is not None else None
            if relative_volume is not None:
                (evidence if relative_volume < 1 else contradictions).append(f"Recent volume is {relative_volume:.2f}× its baseline.")
            if getattr(context.volume_structure, "effort_result_state", None) == "ABSORPTION":
                contradictions.append("High effort with limited price result indicates absorption, not simple volume contraction.")

        returns = c.close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        recent_volatility = self._std(returns.tail(cfg.volatility_window))
        baseline_volatility = self._std(returns.tail(max(cfg.baseline_atr_window, cfg.volatility_window*2)))
        volatility_ratio = self._ratio(recent_volatility, baseline_volatility)
        if baseline_volatility in (None, 0) or volatility_ratio is None:
            flags.append("VOLATILITY_UNAVAILABLE"); volatility_score = None
        else:
            volatility_score = self._ratio_score(volatility_ratio)

        active_low, active_high = float(recent_slice.low.min()), float(recent_slice.high.max())
        containment = float(c.close.tail(cfg.baseline_range_window).between(active_low, active_high).mean())
        duration = self._duration(c.close, active_low, active_high)
        time_score = self._clamp(containment*70 + min(duration/cfg.baseline_range_window, 1)*30)
        if not np.isfinite(time_score):
            time_score = None; flags.append("TIME_COMPRESSION_UNAVAILABLE")

        oi_score, proxy = self._oi(context)
        if oi_score is None: flags.append("OI_UNAVAILABLE")
        if proxy: flags.append("OI_PROXY_ONLY")
        components = {"atr": atr_score, "range": range_score, "spread": spread_score,
                      "volume": volume_score, "volatility": volatility_score,
                      "time": time_score, "oi": oi_score}
        weights = {key: getattr(cfg, f"{key}_weight") for key in components}
        compression = self._weighted(components, weights)
        available = [v for v in components.values() if v is not None]
        agreement = 100-max(available)+min(available) if available else 0
        if available and max(available)-min(available) > 55:
            flags.append("COMPONENTS_CONFLICTED")
        energy = self._clamp(compression*.58 + (time_score or 0)*.22 + (oi_score or 0)*.12 + agreement*.08)

        prior = c.iloc[:-2].tail(cfg.recent_range_window)
        prior_low, prior_high = float(prior.low.min()), float(prior.high.max())
        last = c.iloc[-1]
        breakout = last.close > prior_high or last.close < prior_low
        spread_turn = float(spreads.tail(2).mean()) > float(spreads.iloc[-7:-2].mean())*1.2
        atr_turn = float(tr.tail(2).mean()) > float(tr.iloc[-7:-2].mean())*1.15
        follow = ((c.close.tail(2) > prior_high).all() or (c.close.tail(2) < prior_low).all())
        volume_turn = relative_volume is not None and float(c.volume.tail(2).mean()) > recent_volume*1.15
        readiness = self._clamp(energy*.25 + 25*breakout + 20*spread_turn + 15*atr_turn + 10*volume_turn + 15*follow)
        state = self._state(compression, cfg)
        if breakout and follow and spread_turn and readiness >= cfg.expansion_threshold: state = "EXPANDING"
        elif breakout or (spread_turn and atr_turn and compression >= cfg.moderate_threshold): state = "RELEASING"
        direction = self._direction(context, c, prior_low, prior_high)
        if state in {"RELEASING", "EXPANDING"}: evidence.append(f"Completed candles show {state.lower()} evidence.")
        elif compression < cfg.early_threshold: flags.append("COMPRESSION_UNCONFIRMED")
        confidence = self._clamp(92-len(set(flags))*6-malformed*2-(100-agreement)*.12)
        if any(x in flags for x in ("VOLUME_UNAVAILABLE", "OI_UNAVAILABLE")):
            confidence = min(confidence, cfg.missing_data_confidence_ceiling)
        if proxy: confidence = min(confidence, cfg.proxy_oi_confidence_ceiling)
        self._dependency_flags(context, flags)
        if "STALE_DATA" in flags: confidence = min(confidence, cfg.missing_data_confidence_ceiling)
        label = state.replace("_", " ").title()
        meaning = self._meaning(state)
        explanations = (f"Compression combines {len(available)} available components with normalized configured weights.",
                        "Energy and readiness are estimates, not guarantees of a future move.",
                        "Compression intelligence is informational only and does not alter recommendations.")
        return CompressionIntelligence(state, label, meaning, self._round(compression), self._round(energy),
            self._round(readiness), self._optional(atr_score), self._optional(range_score),
            self._optional(spread_score), self._optional(volume_score), self._optional(volatility_score),
            self._optional(time_score), self._optional(oi_score), self._raw(recent_atr),
            self._raw(baseline_atr), self._raw(atr_ratio), self._raw(recent_range),
            self._raw(baseline_range), self._raw(range_ratio), self._raw(recent_volume),
            self._raw(baseline_volume), self._raw(relative_volume), duration, direction,
            self._round(confidence), tuple(dict.fromkeys(evidence)), tuple(dict.fromkeys(contradictions)),
            tuple(dict.fromkeys(flags)), explanations)

    @classmethod
    def _candles(cls, raw, timestamps):
        if raw is None: return None, ("CANDLES_MISSING",), 0
        try: frame = raw.copy(deep=True) if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        except (TypeError, ValueError): return None, ("OHLC_INVALID",), 0
        if frame.empty: return None, ("CANDLES_MISSING",), 0
        renamed = {}
        for canonical, aliases in cls.ALIASES.items():
            source = next((name for name in aliases if name in frame.columns), None)
            if source is not None: renamed[source] = canonical
        frame = frame.rename(columns=renamed)
        if not {"open", "high", "low", "close"}.issubset(frame): return None, ("OHLC_INVALID",), 0
        for name in ("open", "high", "low", "close", "volume"):
            if name in frame: frame[name] = pd.to_numeric(frame[name], errors="coerce")
        before = len(frame)
        valid = frame[["open", "high", "low", "close"]].notna().all(axis=1)
        valid &= (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
        valid &= frame.high >= frame[["open", "close", "low"]].max(axis=1)
        valid &= frame.low <= frame[["open", "close", "high"]].min(axis=1)
        frame = frame.loc[valid].copy()
        malformed = before-len(frame)
        if frame.empty: return None, ("OHLC_INVALID",), malformed
        flags = ["OHLC_INVALID"] if malformed else []
        if "timestamp" in frame:
            frame["timestamp"] = pd.to_datetime(frame.timestamp, errors="coerce", utc=True)
            bad = int(frame.timestamp.isna().sum()); malformed += bad
            frame = frame.dropna(subset=["timestamp"]).drop_duplicates("timestamp", keep="last").sort_values("timestamp")
            cutoff = cls._cutoff(timestamps)
            if cutoff is not None: frame = frame[frame.timestamp <= cutoff]
            if not frame.empty and (datetime.now(timezone.utc)-frame.timestamp.iloc[-1].to_pydatetime()).total_seconds() > 1800:
                flags.append("STALE_DATA")
        return (frame.reset_index(drop=True), tuple(flags), malformed) if not frame.empty else (None, ("OHLC_INVALID",), malformed)

    @staticmethod
    def _cutoff(timestamps):
        for key in ("analysis_cutoff", "as_of", "last_refresh"):
            value = (timestamps or {}).get(key)
            if not value: continue
            parsed = pd.to_datetime(value, errors="coerce", utc=True)
            if pd.notna(parsed): return parsed
        return None

    @staticmethod
    def _context(value):
        if isinstance(value, DecisionContext): return value
        if not isinstance(value, Mapping): raise TypeError
        snapshot = MarketSnapshot.from_legacy(value)
        return DecisionContext(market_snapshot=snapshot, recommendation=value.get("recommendation") or {},
            engine_results=value.get("engine_results") or {}, configuration=value.get("configuration") or {},
            runtime_configuration=value.get("runtime_configuration") or {}, institutional_metrics=value.get("institutional_metrics"),
            market_location=value.get("market_location"), volume_structure=value.get("volume_structure"),
            positioning_intelligence=value.get("positioning_intelligence"))

    @staticmethod
    def _oi(context):
        metrics = context.institutional_metrics
        if metrics is None: return None, False
        oi = getattr(metrics, "oi", None)
        velocities = [getattr(oi, "call_oi_velocity", None), getattr(oi, "put_oi_velocity", None)]
        available = [float(v) for v in velocities if v is not None and np.isfinite(v)]
        if available: return CompressionIntelligenceEngine._clamp(50+sum(available)*5), False
        summary = context.market_snapshot.option_result.get("summary") or {}
        if summary.get("oi_proxy") or summary.get("futures_oi_proxy"):
            change = sum((getattr(oi, "call_oi_change", 0), getattr(oi, "put_oi_change", 0)))
            return CompressionIntelligenceEngine._clamp(50+change*.01), True
        return None, False

    @staticmethod
    def _direction(context, c, low, high):
        signals = []
        location = context.market_location
        loc = str(getattr(location, "direction", "UNKNOWN"))
        transition = str(getattr(location, "transition", ""))
        volume = str(getattr(context.volume_structure, "direction", "UNKNOWN"))
        positioning = context.positioning_intelligence
        bias = str(getattr(positioning, "overall_bias", "UNKNOWN"))
        for value in (loc, transition, volume, bias):
            upper = value.upper()
            if any(x in upper for x in ("BULL", "UP", "LONG")): signals.append(1)
            elif any(x in upper for x in ("BEAR", "DOWN", "SHORT")): signals.append(-1)
        if c.close.iloc[-1] > high: signals.append(1)
        elif c.close.iloc[-1] < low: signals.append(-1)
        if not signals: return "UNKNOWN"
        if 1 in signals and -1 in signals: return "UNCONFIRMED"
        if len(signals) < 2: return "UNCONFIRMED"
        return "BULLISH_LEAN" if signals[0] > 0 else "BEARISH_LEAN"

    @staticmethod
    def _dependency_flags(context, flags):
        if context.market_location is None: flags.append("MARKET_LOCATION_UNAVAILABLE")
        if context.volume_structure is None: flags.append("VOLUME_STRUCTURE_UNAVAILABLE")
        if context.positioning_intelligence is None: flags.append("POSITIONING_UNAVAILABLE")

    @staticmethod
    def _unavailable(flags):
        return CompressionIntelligence(quality_flags=tuple(dict.fromkeys((*flags, "COMPRESSION_UNCONFIRMED"))),
            explanations=("Compression intelligence is unavailable.", "No recommendation is created or changed."))
    @staticmethod
    def _state(score, cfg):
        if score < cfg.early_threshold: return "NO_COMPRESSION"
        if score < cfg.moderate_threshold: return "EARLY_COMPRESSION"
        if score < cfg.high_threshold: return "MODERATE_COMPRESSION"
        if score < cfg.extreme_threshold: return "HIGH_COMPRESSION"
        return "EXTREME_COMPRESSION"
    @staticmethod
    def _meaning(state):
        return {"NO_COMPRESSION":"The completed-candle structure is not materially compressed.",
            "EARLY_COMPRESSION":"Early narrowing is present but remains unconfirmed.",
            "MODERATE_COMPRESSION":"Several measures show a developing compressed structure.",
            "HIGH_COMPRESSION":"The completed-candle structure is tightly compressed.",
            "EXTREME_COMPRESSION":"Compression is extreme; timing and direction remain unguaranteed.",
            "RELEASING":"A prior compressed structure is beginning to release.",
            "EXPANDING":"Completed candles show a material exit with follow-through."}.get(state, "Compression is unavailable.")
    @staticmethod
    def _duration(series, low, high):
        count = 0
        for value in reversed(series.tolist()):
            if low <= value <= high: count += 1
            else: break
        return count
    @staticmethod
    def _weighted(values, weights):
        available = [(v, weights[k]) for k, v in values.items() if v is not None and weights[k] > 0]
        return CompressionIntelligenceEngine._clamp(sum(v*w for v, w in available)/sum(w for _, w in available)) if available else 0.0
    @staticmethod
    def _ratio_score(ratio): return CompressionIntelligenceEngine._clamp((1-ratio)*125+25)
    @staticmethod
    def _ratio(a, b): return a/b if a is not None and b is not None and b > 0 else None
    @staticmethod
    def _mean(v): return float(v.mean()) if len(v) and pd.notna(v.mean()) else None
    @staticmethod
    def _median(v): return float(v.median()) if len(v) and pd.notna(v.median()) else None
    @staticmethod
    def _std(v): return float(v.std(ddof=0)) if len(v) > 1 and pd.notna(v.std(ddof=0)) else None
    @staticmethod
    def _clamp(v): return max(0.0, min(100.0, float(v)))
    @staticmethod
    def _round(v): return round(CompressionIntelligenceEngine._clamp(v), 4)
    @staticmethod
    def _optional(v): return None if v is None else round(CompressionIntelligenceEngine._clamp(v), 4)
    @staticmethod
    def _raw(v): return None if v is None else round(float(v), 6)
