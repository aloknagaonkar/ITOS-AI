"""Explainable, informational manipulation and trap intelligence.

The scores describe observable failed-acceptance behaviour.  They are not proof
of intent and are never used to create or alter a recommendation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .decision_context import DecisionContext, MarketSnapshot


@dataclass(frozen=True)
class ManipulationIntelligence:
    state: str
    display_label: str
    meaning: str
    market_impact: str
    manipulation_probability: float
    trap_severity: float
    breakout_quality: float
    follow_through_quality: float
    liquidity_sweep_detected: bool
    liquidity_sweep_side: str
    stop_hunt_probability: float
    bull_trap_risk: float
    bear_trap_risk: float
    false_breakout_detected: bool
    false_breakdown_detected: bool
    rejection_score: float
    wick_score: float
    return_inside_range: bool
    range_reentry_speed: float | None
    confirmation_candles: int
    direction: str
    confidence: float
    evidence: tuple[str, ...]
    contradictions: tuple[str, ...]
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]

    @property
    def risk_label(self) -> str:
        if self.manipulation_probability < 25: return "Low"
        if self.manipulation_probability < 45: return "Developing"
        if self.manipulation_probability < 65: return "Moderate"
        if self.manipulation_probability < 85: return "High"
        return "Very High"


@dataclass(frozen=True)
class ManipulationIntelligenceSettings:
    breakout_minimum_distance: float = 0.001
    breakdown_minimum_distance: float = 0.001
    level_proximity_tolerance: float = 0.003
    wick_ratio_threshold: float = 0.35
    rejection_threshold: float = 45.0
    range_reentry_threshold: float = 0.0
    fast_reentry_candle_window: int = 2
    follow_through_candle_count: int = 3
    minimum_confirmation_candles: int = 2
    minimum_candles: int = 6
    volume_expansion_threshold: float = 1.25
    effort_result_imbalance_threshold: float = 0.35
    stop_hunt_threshold: float = 60.0
    liquidity_sweep_threshold: float = 45.0
    bull_trap_threshold: float = 65.0
    bear_trap_threshold: float = 65.0
    possible_threshold: float = 25.0
    moderate_threshold: float = 45.0
    high_threshold: float = 65.0
    confirmed_threshold: float = 85.0
    range_reentry_weight: float = 24.0
    failed_move_weight: float = 18.0
    wick_rejection_weight: float = 14.0
    poor_follow_through_weight: float = 14.0
    effort_result_weight: float = 8.0
    sweep_weight: float = 10.0
    context_weight: float = 6.0
    legacy_agreement_weight: float = 6.0
    trap_distance_weight: float = 30.0
    trap_speed_weight: float = 25.0
    trap_reversal_weight: float = 25.0
    trap_volume_weight: float = 20.0
    breakout_acceptance_weight: float = 45.0
    breakout_follow_through_weight: float = 35.0
    breakout_volume_weight: float = 20.0
    follow_close_weight: float = 60.0
    follow_distance_weight: float = 25.0
    follow_volume_weight: float = 15.0
    contradiction_penalty: float = 12.0
    missing_data_confidence_ceiling: float = 35.0
    stale_data_threshold: int = 1800

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ManipulationIntelligenceSettings":
        raw = (value or {}).get("manipulation_intelligence", value or {})
        allowed = {item.name for item in fields(cls)}
        try:
            return cls(**{key: raw[key] for key in allowed if key in raw})
        except (TypeError, ValueError):
            return cls()


_DEFINITIONS = {
    "NO_MANIPULATION": ("No Significant Manipulation", "The current move does not show strong trap or liquidity-sweep evidence.", "The move may still fail, but available evidence does not currently suggest significant manipulation."),
    "POSSIBLE_MANIPULATION": ("Possible Manipulation", "The move shows some trap-like behaviour but is not yet confirmed.", "Wait for follow-through before trusting the move."),
    "LIQUIDITY_SWEEP": ("Liquidity Sweep", "Price moved beyond a key level, collected liquidity, and returned toward the previous range.", "The initial breach may not represent genuine directional intent."),
    "STOP_HUNT_RISK": ("Stop-Hunt Risk", "Price may have moved beyond a known level where stop losses can cluster.", "Avoid reacting immediately until price acceptance or rejection is confirmed."),
    "BULL_TRAP_RISK": ("Bull-Trap Risk", "Buyers may have entered a breakout that failed to hold.", "Upside participants may be trapped if price remains below resistance."),
    "BEAR_TRAP_RISK": ("Bear-Trap Risk", "Sellers may have entered a breakdown that failed to hold.", "Downside participants may be trapped if price remains above support."),
    "FALSE_BREAKOUT": ("False Breakout", "Price moved above resistance but failed to sustain above it.", "The breakout should not be treated as genuine without renewed acceptance."),
    "FALSE_BREAKDOWN": ("False Breakdown", "Price moved below support but failed to sustain below it.", "The breakdown should not be treated as genuine without renewed acceptance."),
    "MANIPULATION_CONFIRMED": ("High Manipulation Risk", "Multiple independent signals indicate a likely trap or liquidity-collection event.", "Avoid directional entries until acceptance is established outside the affected area."),
    "UNAVAILABLE": ("Manipulation Intelligence Unavailable", "Required range, candle, or follow-through data is unavailable.", "No manipulation conclusion can be made from the available data."),
}


class ManipulationIntelligenceEngine:
    """Evaluate completed candles and supplied typed context without side effects."""

    def __init__(self, settings: ManipulationIntelligenceSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, value: DecisionContext | Mapping[str, Any]) -> ManipulationIntelligence:
        context = self._context(value)
        cfg = self.settings or ManipulationIntelligenceSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        flags: list[str] = []
        candles = self._candles(context.market_snapshot.historical_candles, flags)
        if candles is None:
            return self._unavailable(flags)
        if len(candles) < cfg.minimum_candles:
            return self._unavailable((*flags, "CANDLES_INSUFFICIENT"))

        location = context.market_location
        support = self._number(getattr(location, "support_level", None))
        resistance = self._number(getattr(location, "resistance_level", None))
        if location is None or getattr(location, "zone", "UNKNOWN") == "UNKNOWN":
            flags.append("MARKET_LOCATION_UNAVAILABLE")
        if support is None: flags.append("SUPPORT_UNAVAILABLE")
        if resistance is None: flags.append("RESISTANCE_UNAVAILABLE")
        if support is None and resistance is None:
            flags.append("RANGE_UNAVAILABLE")
            return self._unavailable(flags)

        volume_structure = context.volume_structure
        positioning = context.positioning_intelligence
        compression = context.compression_intelligence
        legacy = context.false_breakout_result
        if volume_structure is None: flags.append("VOLUME_STRUCTURE_UNAVAILABLE")
        if positioning is None: flags.append("POSITIONING_UNAVAILABLE")
        if compression is None: flags.append("COMPRESSION_UNAVAILABLE")
        if legacy is None: flags.append("FALSE_BREAKOUT_EVIDENCE_UNAVAILABLE")
        self._stale(candles, context, cfg, flags)

        last = candles.iloc[-1]
        spread = float(last.high-last.low)
        if spread <= 0:
            return self._unavailable((*flags, "ZERO_WIDTH_CANDLE"))
        body = abs(float(last.close-last.open))
        upper = float(last.high-max(last.open, last.close))
        lower = float(min(last.open, last.close)-last.low)
        upper_ratio, lower_ratio = upper/spread, lower/spread
        wick = self._clamp(max(upper_ratio, lower_ratio)*100)

        lookback = candles.tail(cfg.follow_through_candle_count + cfg.fast_reentry_candle_window + 2)
        above = resistance is not None and bool((lookback.high > resistance*(1+cfg.breakout_minimum_distance)).any())
        below = support is not None and bool((lookback.low < support*(1-cfg.breakdown_minimum_distance)).any())
        current_inside_above = resistance is not None and float(last.close) <= resistance*(1+cfg.range_reentry_threshold)
        current_inside_below = support is not None and float(last.close) >= support*(1-cfg.range_reentry_threshold)
        failed_up = bool(above and current_inside_above)
        failed_down = bool(below and current_inside_below)
        return_inside = failed_up or failed_down
        reentry_up = self._reentry_speed(lookback, resistance, True) if above else None
        reentry_down = self._reentry_speed(lookback, support, False) if below else None
        speeds = [item for item in (reentry_up, reentry_down) if item is not None]
        speed = min(speeds) if speeds else None

        confirmations = 0
        level = resistance if above and not below else support
        direction_up = above and not below
        if level is not None:
            recent = candles.close.tail(cfg.follow_through_candle_count)
            confirmations = int((recent > level).sum() if direction_up else (recent < level).sum())
        if len(candles) < cfg.follow_through_candle_count:
            flags.append("FOLLOW_THROUGH_INSUFFICIENT")
        follow = self._follow_quality(candles, level, direction_up, volume_structure, cfg) if level is not None else 50.0
        acceptance = confirmations/max(cfg.follow_through_candle_count, 1)*100
        volume_confirmation = getattr(volume_structure, "volume_confirmation", "UNAVAILABLE")
        volume_component = 100.0 if volume_confirmation == "CONFIRMED" else 20.0 if volume_confirmation in {"DIVERGING", "DIVERGENT"} else 50.0
        breakout_quality = self._clamp(
            acceptance*cfg.breakout_acceptance_weight/100
            + follow*cfg.breakout_follow_through_weight/100
            + volume_component*cfg.breakout_volume_weight/100
            - (35 if return_inside else 0)
            - wick*0.20
        )
        rejection = self._clamp((upper_ratio*100 if failed_up else lower_ratio*100 if failed_down else wick*.35) + (25 if return_inside else 0))
        sweep_up = failed_up and rejection >= cfg.rejection_threshold
        sweep_down = failed_down and rejection >= cfg.rejection_threshold
        sweep = sweep_up or sweep_down
        sweep_side = "BOTH" if sweep_up and sweep_down else "ABOVE_RESISTANCE" if sweep_up else "BELOW_SUPPORT" if sweep_down else "NONE"

        evidence: list[str] = []
        contradictions: list[str] = []
        if failed_up: evidence.append("Price breached resistance and subsequently closed back inside the prior range.")
        if failed_down: evidence.append("Price breached support and subsequently reclaimed the prior range.")
        if sweep: evidence.append(f"Rejection around {sweep_side.lower().replace('_', ' ')} is consistent with liquidity-sweep behaviour.")
        if wick >= cfg.wick_ratio_threshold*100: evidence.append(f"The completed candle has a {wick:.1f}% opposing wick-to-spread ratio.")
        elif wick > 0: contradictions.append("Wick rejection is below the configured meaningful threshold.")
        if follow >= 65: contradictions.append("Completed candles show healthy directional follow-through.")
        else: evidence.append("Completed-candle follow-through is weak.")
        effort_imbalance = getattr(volume_structure, "effort_result_state", "") == "ABSORPTION"
        if effort_imbalance: evidence.append("Volume structure reports high effort with limited directional result.")

        legacy_agrees = self._legacy_agrees(legacy, failed_up, failed_down)
        if legacy_agrees is True: evidence.append("Existing false-breakout evidence agrees with the failed move.")
        elif legacy_agrees is False: contradictions.append("Existing false-breakout evidence does not agree with the candidate.")

        location_relevant = getattr(location, "zone", "UNKNOWN") in {"TOP", "UPPER_RANGE", "BOTTOM", "LOWER_RANGE", "BREAKOUT_ZONE", "RETEST_ZONE"}
        probability = (
            (cfg.range_reentry_weight if return_inside else 0)
            + (cfg.failed_move_weight if failed_up or failed_down else 0)
            + rejection*cfg.wick_rejection_weight/100
            + (100-follow)*cfg.poor_follow_through_weight/100
            + (cfg.effort_result_weight if effort_imbalance else 0)
            + (cfg.sweep_weight if sweep else 0)
            + (cfg.context_weight if location_relevant else 0)
            + (cfg.legacy_agreement_weight if legacy_agrees else 0)
            - len(contradictions)*cfg.contradiction_penalty
        )
        comp_state = str(getattr(compression, "state", "UNAVAILABLE"))
        if comp_state in {"RELEASING", "HIGH_COMPRESSION"}:
            if return_inside: probability += cfg.context_weight
            elif follow >= 65: probability -= cfg.context_weight
        probability = self._clamp(probability)

        fast = speed is not None and speed <= cfg.fast_reentry_candle_window
        stop_hunt = self._clamp(rejection*.35 + (30 if fast else 0) + (20 if effort_imbalance else 0) + (15 if sweep else 0))
        bull = self._clamp(probability + (15 if failed_up else -20) + (10 if getattr(location, "zone", "") in {"TOP", "UPPER_RANGE"} else 0)) if failed_up else 0.0
        bear = self._clamp(probability + (15 if failed_down else -20) + (10 if getattr(location, "zone", "") in {"BOTTOM", "LOWER_RANGE"} else 0)) if failed_down else 0.0
        bias = getattr(positioning, "overall_bias", "UNKNOWN")
        if failed_up and bias == "BULLISH":
            bull = self._clamp(bull-cfg.contradiction_penalty); contradictions.append("Bullish positioning contradicts the bull-trap interpretation.")
        if failed_down and bias == "BEARISH":
            bear = self._clamp(bear-cfg.contradiction_penalty); contradictions.append("Bearish positioning contradicts the bear-trap interpretation.")
        if failed_up and failed_down: flags.append("TRAP_DIRECTION_CONFLICTED")
        severity = self._clamp(
            rejection*cfg.trap_distance_weight/100
            + (100 if fast else 35)*cfg.trap_speed_weight/100
            + (100-follow)*cfg.trap_reversal_weight/100
            + (100 if effort_imbalance else 35)*cfg.trap_volume_weight/100
        ) if return_inside else 0.0

        state = self._state(probability, failed_up, failed_down, sweep, stop_hunt, bull, bear, cfg)
        if probability >= cfg.possible_threshold and state == "POSSIBLE_MANIPULATION": flags.append("MANIPULATION_UNCONFIRMED")
        direction = "NEUTRAL" if failed_up and failed_down else "BEARISH_TRAP" if failed_up else "BULLISH_TRAP" if failed_down else "NEUTRAL"
        confidence = self._clamp(35 + min(len(evidence), 5)*10 + (15 if return_inside else 0) - len(contradictions)*6)
        critical = {"VOLUME_STRUCTURE_UNAVAILABLE", "MARKET_LOCATION_UNAVAILABLE", "FOLLOW_THROUGH_INSUFFICIENT", "STALE_DATA"}
        if critical.intersection(flags): confidence = min(confidence, cfg.missing_data_confidence_ceiling)
        if not evidence: evidence.append("No completed-candle failed-acceptance event was identified.")
        definition = _DEFINITIONS[state]
        explanations = (
            f"What happened: {evidence[0]}",
            f"What it may imply: {definition[2]}",
            "This evidence score is informational and does not assert deliberate intent or alter the recommendation.",
        )
        return ManipulationIntelligence(
            state, *definition, round(probability, 4), round(severity, 4), round(breakout_quality, 4), round(follow, 4),
            sweep, sweep_side, round(stop_hunt, 4), round(bull, 4), round(bear, 4), failed_up, failed_down,
            round(rejection, 4), round(wick, 4), return_inside, float(speed) if speed is not None else None,
            confirmations, direction, round(confidence, 4), tuple(evidence), tuple(contradictions),
            tuple(dict.fromkeys(flags)), explanations,
        )

    @staticmethod
    def _context(value: DecisionContext | Mapping[str, Any]) -> DecisionContext:
        if isinstance(value, DecisionContext): return value
        snapshot = MarketSnapshot.from_legacy(value)
        return DecisionContext(
            market_snapshot=snapshot, recommendation=value.get("recommendation") or {},
            engine_results=value.get("engine_results") or {}, configuration=value.get("configuration") or {},
            runtime_configuration=value.get("runtime_configuration") or {},
            market_location=value.get("market_location"), volume_structure=value.get("volume_structure"),
            positioning_intelligence=value.get("positioning_intelligence"), compression_intelligence=value.get("compression_intelligence"),
            false_breakout_result=value.get("false_breakout_result", value.get("false_breakout")),
        )

    @staticmethod
    def _candles(raw: Any, flags: list[str]) -> pd.DataFrame | None:
        if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty): flags.append("CANDLES_MISSING"); return None
        try: frame = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        except (TypeError, ValueError): flags.append("OHLC_INVALID"); return None
        required = ["open", "high", "low", "close"]
        if any(key not in frame for key in required): flags.append("OHLC_INVALID"); return None
        numeric = frame[required].apply(pd.to_numeric, errors="coerce")
        if numeric.isna().any().any() or (numeric.high < numeric.low).any(): flags.append("OHLC_INVALID"); return None
        frame[required] = numeric
        if "volume" not in frame: flags.append("VOLUME_UNAVAILABLE")
        else:
            frame["volume"] = pd.to_numeric(frame.volume, errors="coerce")
            if frame.volume.isna().any(): flags.append("VOLUME_UNAVAILABLE")
        return frame

    @staticmethod
    def _follow_quality(candles, level, upward, volume_structure, cfg):
        recent = candles.tail(cfg.follow_through_candle_count)
        outside = (recent.close > level) if upward else (recent.close < level)
        close_score = float(outside.mean())*100
        distance = ((recent.close-level)/max(abs(level), 1e-9)) if upward else ((level-recent.close)/max(abs(level), 1e-9))
        distance_score = max(0.0, min(100.0, float(distance.mean())/max(cfg.breakout_minimum_distance, 1e-9)*50))
        volume_score = 100.0 if getattr(volume_structure, "volume_confirmation", "") == "CONFIRMED" else 40.0
        return ManipulationIntelligenceEngine._clamp(close_score*cfg.follow_close_weight/100 + distance_score*cfg.follow_distance_weight/100 + volume_score*cfg.follow_volume_weight/100)

    @staticmethod
    def _reentry_speed(candles, level, above):
        if level is None: return None
        breached = candles.high > level if above else candles.low < level
        indices = [i for i, hit in enumerate(breached.tolist()) if hit]
        if not indices: return None
        first = indices[-1]
        closes = candles.close.tolist()
        for index in range(first, len(closes)):
            if (closes[index] <= level if above else closes[index] >= level): return index-first
        return None

    @staticmethod
    def _legacy_agrees(result, up, down):
        if result is None: return None
        metadata = getattr(result, "metadata", result if isinstance(result, Mapping) else {}) or {}
        blocked = bool(metadata.get("blocked", False))
        text = " ".join(str(value).lower() for value in metadata.values())
        reports_up = blocked or "false breakout" in text or "bull trap" in text
        reports_down = "false breakdown" in text or "bear trap" in text
        return bool((up and reports_up) or (down and reports_down)) if up or down else None

    @staticmethod
    def _state(probability, up, down, sweep, stop, bull, bear, cfg):
        if probability >= cfg.confirmed_threshold and (up or down) and sweep: return "MANIPULATION_CONFIRMED"
        if up and down: return "MANIPULATION_CONFIRMED" if probability >= cfg.high_threshold else "POSSIBLE_MANIPULATION"
        if up and probability >= cfg.moderate_threshold: return "FALSE_BREAKOUT"
        if down and probability >= cfg.moderate_threshold: return "FALSE_BREAKDOWN"
        if sweep: return "LIQUIDITY_SWEEP"
        if stop >= cfg.stop_hunt_threshold: return "STOP_HUNT_RISK"
        if bull >= cfg.bull_trap_threshold: return "BULL_TRAP_RISK"
        if bear >= cfg.bear_trap_threshold: return "BEAR_TRAP_RISK"
        return "POSSIBLE_MANIPULATION" if probability >= cfg.possible_threshold else "NO_MANIPULATION"

    @staticmethod
    def _number(value):
        try:
            number = float(value)
            return number if pd.notna(number) else None
        except (TypeError, ValueError, OverflowError): return None

    @staticmethod
    def _clamp(value): return max(0.0, min(100.0, float(value)))

    @staticmethod
    def _stale(candles, context, cfg, flags):
        stamp = candles["timestamp"].iloc[-1] if "timestamp" in candles else context.market_snapshot.timestamps.get("captured_at")
        if stamp is None: return
        try:
            parsed = pd.Timestamp(stamp)
            if parsed.tzinfo is None: parsed = parsed.tz_localize("UTC")
            if (datetime.now(timezone.utc)-parsed.to_pydatetime()).total_seconds() > cfg.stale_data_threshold: flags.append("STALE_DATA")
        except (TypeError, ValueError, OverflowError): flags.append("STALE_DATA")

    @staticmethod
    def _unavailable(flags) -> ManipulationIntelligence:
        label, meaning, impact = _DEFINITIONS["UNAVAILABLE"]
        return ManipulationIntelligence("UNAVAILABLE", label, meaning, impact, 0.0, 0.0, 0.0, 0.0, False, "UNKNOWN", 0.0, 0.0, 0.0, False, False, 0.0, 0.0, False, None, 0, "UNKNOWN", 5.0, (), ("Critical completed-candle or range evidence is unavailable.",), tuple(dict.fromkeys(flags)), ("What happened: required evidence could not be validated.", "What it may imply: no manipulation conclusion is available.", "This result is informational only."))
