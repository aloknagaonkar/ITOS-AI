"""Explainable, decision-neutral futures and options positioning intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .decision_context import DecisionContext


@dataclass(frozen=True)
class PositioningState:
    state: str
    meaning: str
    market_impact: str
    confidence: float
    evidence: tuple[str, ...]
    contradictions: tuple[str, ...]
    quality_flags: tuple[str, ...] = ()

    @property
    def display_state(self) -> str:
        return self.state.replace("_", " ").title()


@dataclass(frozen=True)
class PositioningIntelligence:
    futures: PositioningState
    options: PositioningState
    overall_bias: str
    overall_confidence: float
    dominant_state: str
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]


@dataclass(frozen=True)
class PositioningIntelligenceSettings:
    price_neutral_threshold: float = 0.10
    oi_neutral_threshold: float = 0.10
    minimum_oi_change: float = 1.0
    minimum_volume_confirmation: float = 10.0
    writing_score_threshold: float = 1.0
    buying_score_threshold: float = 1.0
    premium_change_threshold: float = 0.05
    iv_confirmation_threshold: float = 0.10
    liquidity_minimum: float = 25.0
    price_oi_weight: float = 45.0
    volume_weight: float = 15.0
    premium_weight: float = 20.0
    liquidity_weight: float = 10.0
    context_weight: float = 10.0
    conflict_penalty: float = 25.0
    missing_data_confidence_ceiling: float = 40.0
    proxy_data_confidence_ceiling: float = 55.0
    stale_data_threshold: int = 1800

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "PositioningIntelligenceSettings":
        raw = (value or {}).get("positioning_intelligence", value or {})
        allowed = {item.name for item in fields(cls)}
        try:
            return cls(**{key: raw[key] for key in allowed if key in raw})
        except (TypeError, ValueError):
            return cls()


_TEXT = {
    "LONG_BUILDUP": ("New buyers are entering the market.", "Fresh bullish positions are being opened. The move may be more sustainable when volume, structure and institutional flow also confirm."),
    "SHORT_BUILDUP": ("New sellers are entering the market.", "Fresh bearish positions are being opened. Downside pressure may continue when volume and structure confirm."),
    "SHORT_COVERING": ("Existing short sellers are exiting their positions.", "Short sellers are buying back positions. This can create a sharp rally, but the move may be less sustainable without fresh long build-up."),
    "LONG_UNWINDING": ("Existing buyers are exiting their positions.", "Existing long positions are being reduced. Price may weaken, but this is not the same as aggressive fresh short selling."),
    "PUT_WRITING": ("Option sellers are creating possible support.", "Participants are selling put options and may expect price to remain above the relevant strikes. Treat support as conditional, not guaranteed."),
    "CALL_WRITING": ("Option sellers are creating possible resistance.", "Participants are selling call options and may expect price to remain below the relevant strikes. Treat resistance as conditional, not guaranteed."),
    "CALL_BUYING": ("Buyers are seeking bullish exposure or hedging.", "Call demand may support bullish expectations, but rising IV or hedging activity can create similar behaviour."),
    "PUT_BUYING": ("Buyers are seeking bearish exposure or protection.", "Put demand may reflect bearish expectations or portfolio protection. Do not assume it is always an outright bearish directional bet."),
    "MIXED": ("Buying and writing evidence is conflicting.", "Conflicting options activity does not provide a reliable directional implication yet."),
    "NEUTRAL": ("Positioning is balanced or inside the neutral bands.", "Evidence does not yet suggest a strong positioning state."),
    "UNAVAILABLE": ("Positioning evidence is not available yet.", "No market impact is inferred from incomplete positioning data."),
}


class PositioningIntelligenceEngine:
    """Classify supplied measurements without repositories, UI, or trade effects."""

    def __init__(self, settings: PositioningIntelligenceSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, context: DecisionContext) -> PositioningIntelligence:
        settings = self.settings or PositioningIntelligenceSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        futures = self._futures(context, settings)
        options = self._options(context, settings)
        flags = tuple(dict.fromkeys(futures.quality_flags + options.quality_flags))
        bullish = {"LONG_BUILDUP", "SHORT_COVERING", "PUT_WRITING", "CALL_BUYING"}
        bearish = {"SHORT_BUILDUP", "LONG_UNWINDING", "CALL_WRITING", "PUT_BUYING"}
        states = (futures.state, options.state)
        votes = [("BULLISH" if state in bullish else "BEARISH" if state in bearish else None) for state in states]
        valid_votes = [vote for vote in votes if vote]
        bias = (
            "UNKNOWN" if all(state == "UNAVAILABLE" for state in states)
            else "NEUTRAL" if not valid_votes
            else valid_votes[0] if len(set(valid_votes)) == 1 else "CONFLICTED"
        )
        if bias == "CONFLICTED":
            flags = tuple(dict.fromkeys(flags + ("POSITIONING_CONFLICTED",)))
        candidates = [futures, options]
        dominant = max(candidates, key=lambda item: item.confidence)
        if dominant.state in {"UNAVAILABLE", "NEUTRAL", "MIXED"} and all(item.confidence <= 10 for item in candidates):
            dominant_state = "UNAVAILABLE"
        else:
            dominant_state = dominant.state
        available = [item.confidence for item in candidates if item.state != "UNAVAILABLE"]
        confidence = self._clamp(sum(available) / len(available) if available else 0.0)
        if bias == "CONFLICTED":
            confidence = self._clamp(confidence - settings.conflict_penalty)
        return PositioningIntelligence(
            futures, options, bias, confidence, dominant_state, flags,
            ("Positioning intelligence is informational only and does not alter CE, PE, or WAIT decisions.",
             f"Overall evidence is {bias.lower()}; dominant measured state is {dominant_state.replace('_', ' ').title()}.")
        )

    def _futures(self, context: DecisionContext, s: PositioningIntelligenceSettings) -> PositioningState:
        volume = context.volume_structure
        flags: list[str] = []
        evidence: list[str] = []
        contradictions: list[str] = []
        price = self._number(getattr(volume, "price_change_percent", None))
        if price is None:
            intelligence = context.market_snapshot.intelligence
            price_data = intelligence.get("price", {}) if isinstance(intelligence, Mapping) else {}
            price = self._first_number(price_data if isinstance(price_data, Mapping) else {}, ("change_percent", "price_change_percent", "change"))
        if price is None:
            flags.append("PRICE_DIRECTION_UNAVAILABLE")
        summary = context.market_snapshot.option_result.get("summary", {}) if isinstance(context.market_snapshot.option_result, Mapping) else {}
        intelligence = context.market_snapshot.intelligence if isinstance(context.market_snapshot.intelligence, Mapping) else {}
        oi = self._first_number(summary if isinstance(summary, Mapping) else {}, ("futures_oi_change", "futures_oi_change_percent", "underlying_oi_change"))
        if oi is None:
            oi = self._first_number(intelligence, ("futures_oi_change", "futures_oi_change_percent", "underlying_oi_change"))
        proxy = False
        if oi is None:
            oi = self._first_number(summary if isinstance(summary, Mapping) else {}, ("option_oi_change", "total_oi_change"))
            proxy = oi is not None
        if oi is None:
            flags.extend(("OI_UNAVAILABLE", "OI_HISTORY_INSUFFICIENT"))
        elif proxy:
            flags.append("FUTURES_OI_PROXY_ONLY")
        if volume is None:
            flags.append("VOLUME_STRUCTURE_UNAVAILABLE")
        elif "STALE_DATA" in getattr(volume, "quality_flags", ()):
            flags.append("STALE_DATA")
        if context.market_location is None:
            flags.append("MARKET_LOCATION_UNAVAILABLE")
        if price is None or oi is None:
            return self._state("UNAVAILABLE", 0.0, evidence, contradictions, flags)
        price_direction = 1 if price > s.price_neutral_threshold else -1 if price < -s.price_neutral_threshold else 0
        oi_band = max(s.oi_neutral_threshold, s.minimum_oi_change)
        oi_direction = 1 if oi > oi_band else -1 if oi < -oi_band else 0
        evidence.extend((f"Underlying price change is {price:.2f}%.", f"Futures OI change is {oi:.2f}%{' (proxy)' if proxy else ''}."))
        if not price_direction or not oi_direction:
            return self._state("NEUTRAL", 20.0, evidence, contradictions, flags)
        state = {(1, 1): "LONG_BUILDUP", (-1, 1): "SHORT_BUILDUP", (1, -1): "SHORT_COVERING", (-1, -1): "LONG_UNWINDING"}[(price_direction, oi_direction)]
        confidence = s.price_oi_weight
        confirmation = getattr(volume, "volume_confirmation", "UNAVAILABLE")
        strength = self._number(getattr(volume, "volume_strength", None)) or 0.0
        if confirmation == "CONFIRMED" and strength >= s.minimum_volume_confirmation:
            confidence += s.volume_weight
            evidence.append("Price direction is confirmed by measured volume participation.")
        elif confirmation == "DIVERGING":
            confidence -= s.volume_weight
            contradictions.append("Volume diverges from the price move.")
        zone = getattr(context.market_location, "zone", "UNKNOWN")
        if (zone in {"TOP", "UPPER_RANGE"} and state in {"LONG_BUILDUP", "SHORT_COVERING"}) or (zone in {"BOTTOM", "LOWER_RANGE"} and state in {"SHORT_BUILDUP", "LONG_UNWINDING"}):
            confidence -= s.context_weight
            contradictions.append(f"The {zone.replace('_', ' ').lower()} location creates possible climax or reversal risk.")
        elif zone != "UNKNOWN":
            confidence += s.context_weight
            evidence.append(f"Market location ({zone.replace('_', ' ').title()}) is contextually consistent.")
        if proxy:
            confidence = min(confidence, s.proxy_data_confidence_ceiling)
        return self._state(state, confidence, evidence, contradictions, flags)

    def _options(self, context: DecisionContext, s: PositioningIntelligenceSettings) -> PositioningState:
        metrics = context.institutional_metrics
        flags: list[str] = []
        evidence: list[str] = []
        contradictions: list[str] = []
        if metrics is None:
            return self._state("UNAVAILABLE", 0.0, evidence, contradictions, ("INSTITUTIONAL_METRICS_UNAVAILABLE",))
        if "STALE_DATA" in getattr(metrics, "quality_flags", ()):
            flags.append("STALE_DATA")
        chain = context.market_snapshot.option_result.get("chain") if isinstance(context.market_snapshot.option_result, Mapping) else None
        try:
            frame = chain.copy() if isinstance(chain, pd.DataFrame) else pd.DataFrame(chain)
        except (TypeError, ValueError):
            frame = pd.DataFrame()
        aliases = {"call_premium": ("call_price_change", "ce_price_change"), "put_premium": ("put_price_change", "pe_price_change")}
        premium: dict[str, float | None] = {}
        for key, names in aliases.items():
            name = next((name for name in names if name in frame), None)
            values = pd.to_numeric(frame[name], errors="coerce").dropna() if name else pd.Series(dtype=float)
            premium[key] = float(values.mean()) if not values.empty else None
        if any(value is None for value in premium.values()): flags.append("OPTION_PREMIUM_UNAVAILABLE")
        volatility = getattr(metrics, "volatility", None)
        if volatility is None or (getattr(volatility, "call_iv", None) is None and getattr(volatility, "put_iv", None) is None): flags.append("IV_UNAVAILABLE")
        greeks = getattr(metrics, "greeks", None)
        if greeks is None or (getattr(greeks, "call_delta", None) is None and getattr(greeks, "put_delta", None) is None): flags.append("GREEKS_UNAVAILABLE")
        liquidity = getattr(metrics, "liquidity", None)
        liquidity_score = self._number(getattr(liquidity, "liquidity_score", None))
        if liquidity_score is None or liquidity_score < s.liquidity_minimum or bool(getattr(liquidity, "thin_market", False)): flags.append("LIQUIDITY_THIN")
        oi = getattr(metrics, "oi", None); positioning = getattr(metrics, "positioning", None)
        call_oi = self._number(getattr(oi, "call_oi_change", None)) or 0.0
        put_oi = self._number(getattr(oi, "put_oi_change", None)) or 0.0
        call_write = self._number(getattr(positioning, "call_writing_score", None)) or 0.0
        put_write = self._number(getattr(positioning, "put_writing_score", None)) or 0.0
        call_volume = self._number(getattr(liquidity, "call_volume", None)) or 0.0
        put_volume = self._number(getattr(liquidity, "put_volume", None)) or 0.0
        candidates: list[tuple[str, float]] = []
        for side, oi_change, writing, volume_amount in (("CALL", call_oi, call_write, call_volume), ("PUT", put_oi, put_write, put_volume)):
            pchange = premium[f"{side.lower()}_premium"]
            if oi_change < s.minimum_oi_change: continue
            if pchange is None:
                contradictions.append(f"{side.title()} OI increased without premium confirmation.")
                continue
            if pchange <= -s.premium_change_threshold and writing >= s.writing_score_threshold:
                candidates.append((f"{side}_WRITING", writing + abs(oi_change)))
                evidence.append(f"{side.title()} OI increased while premium was stable/falling ({pchange:.2f}); writing score confirms.")
            elif pchange >= s.premium_change_threshold and volume_amount >= s.buying_score_threshold:
                candidates.append((f"{side}_BUYING", volume_amount + abs(oi_change)))
                evidence.append(f"{side.title()} premium and demand rose together ({pchange:.2f}).")
            else:
                contradictions.append(f"{side.title()} OI change lacks a sufficiently strong buying or writing confirmation.")
        if not candidates:
            state = "NEUTRAL" if call_oi or put_oi else "UNAVAILABLE"
            confidence = 10.0 if state == "NEUTRAL" else 0.0
        else:
            ordered = sorted(candidates, key=lambda item: item[1], reverse=True)
            state = ordered[0][0]
            if len(ordered) > 1 and ordered[1][1] >= ordered[0][1] * 0.75:
                state = "MIXED"; flags.append("POSITIONING_CONFLICTED"); contradictions.append("Competing options positioning signals have similar strength.")
            confidence = s.price_oi_weight + s.premium_weight
            confidence += s.liquidity_weight if "LIQUIDITY_THIN" not in flags else -s.liquidity_weight
            if context.market_location is None: flags.append("MARKET_LOCATION_UNAVAILABLE")
            else:
                zone = context.market_location.zone
                consistent = (state == "PUT_WRITING" and zone in {"BOTTOM", "LOWER_RANGE"}) or (state == "CALL_WRITING" and zone in {"TOP", "UPPER_RANGE"})
                confidence += s.context_weight if consistent else 0.0
                if consistent: evidence.append(f"The {zone.replace('_', ' ').lower()} location supports this conditional interpretation.")
        critical = {"OPTION_PREMIUM_UNAVAILABLE", "LIQUIDITY_THIN"}
        if critical.intersection(flags): confidence = min(confidence, s.missing_data_confidence_ceiling)
        return self._state(state, confidence - len(contradictions) * s.conflict_penalty / 2, evidence, contradictions, flags)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            number = float(value)
            return number if pd.notna(number) and number not in (float("inf"), float("-inf")) else None
        except (TypeError, ValueError, OverflowError):
            return None

    def _first_number(self, source: Mapping[str, Any], names: tuple[str, ...]) -> float | None:
        for name in names:
            value = self._number(source.get(name))
            if value is not None: return value
        return None

    @staticmethod
    def _clamp(value: float) -> float:
        return round(max(0.0, min(100.0, value)), 2)

    def _state(self, state: str, confidence: float, evidence: Any, contradictions: Any, flags: Any) -> PositioningState:
        meaning, impact = _TEXT[state]
        return PositioningState(state, meaning, impact, self._clamp(confidence), tuple(evidence), tuple(contradictions), tuple(dict.fromkeys(flags)))
