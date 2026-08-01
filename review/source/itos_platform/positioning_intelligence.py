"""Explainable, decision-neutral futures and options positioning intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from typing import Any

import numpy as np
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
    minimum_volume_confirmation: float = 50.0
    writing_score_threshold: float = 20.0
    buying_score_threshold: float = 20.0
    premium_change_threshold: float = 0.05
    iv_confirmation_threshold: float = 0.10
    liquidity_minimum: float = 25.0
    price_oi_weight: float = 45.0
    volume_weight: float = 15.0
    premium_weight: float = 20.0
    liquidity_weight: float = 10.0
    context_weight: float = 10.0
    conflict_penalty: float = 25.0
    missing_data_confidence_ceiling: float = 45.0
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


_DEFINITIONS = {
    "LONG_BUILDUP": ("New buyers are entering the market.", "Fresh bullish positions are being opened. The move may be more sustainable when volume, structure and institutional flow also confirm."),
    "SHORT_BUILDUP": ("New sellers are entering the market.", "Fresh bearish positions are being opened. Downside pressure may continue when volume and structure confirm."),
    "SHORT_COVERING": ("Existing short sellers are exiting their positions.", "Short sellers are buying back positions. This can create a sharp rally, but the move may be less sustainable without fresh long build-up."),
    "LONG_UNWINDING": ("Existing buyers are exiting their positions.", "Existing long positions are being reduced. Price may weaken, but this is not the same as aggressive fresh short selling."),
    "PUT_WRITING": ("Option sellers are creating possible support.", "Participants are selling put options and may expect price to remain above the relevant strikes. Treat support as conditional, not guaranteed."),
    "CALL_WRITING": ("Option sellers are creating possible resistance.", "Participants are selling call options and may expect price to remain below the relevant strikes. Treat resistance as conditional, not guaranteed."),
    "CALL_BUYING": ("Buyers are seeking bullish exposure or hedging.", "Call demand may support bullish expectations, but rising IV or hedging activity can create similar behaviour."),
    "PUT_BUYING": ("Buyers are seeking bearish exposure or protection.", "Put demand may reflect bearish expectations or portfolio protection. Do not assume it is always an outright bearish directional bet."),
    "MIXED": ("Writing and buying evidence is conflicting.", "Conflicting option activity suggests waiting for clearer confirmation."),
    "NEUTRAL": ("Positioning evidence is currently balanced.", "No clear positioning impact is established yet."),
    "UNAVAILABLE": ("Positioning evidence is not available yet.", "No market impact is inferred from incomplete positioning data."),
}


class PositioningIntelligenceEngine:
    """Classify supplied evidence without repositories, UI, or recommendation changes."""

    def __init__(self, settings: PositioningIntelligenceSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, context: DecisionContext) -> PositioningIntelligence:
        cfg = self.settings or PositioningIntelligenceSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        flags: list[str] = []
        self._context_flags(context, cfg, flags)
        futures = self._futures(context, cfg, flags)
        options = self._options(context, cfg, flags)
        directions = {self._direction(futures.state), self._direction(options.state)} - {"UNKNOWN", "NEUTRAL"}
        if len(directions) > 1:
            bias = "CONFLICTED"
            flags.append("POSITIONING_CONFLICTED")
        elif directions:
            bias = next(iter(directions))
        elif futures.state == options.state == "UNAVAILABLE":
            bias = "UNKNOWN"
        else:
            bias = "NEUTRAL"
        dominant = max((futures, options), key=lambda item: item.confidence)
        if dominant.confidence <= 0 or dominant.state in {"NEUTRAL", "UNAVAILABLE"}:
            dominant_state = "UNAVAILABLE" if bias == "UNKNOWN" else "NEUTRAL"
        else:
            dominant_state = dominant.state
        confidence = self._clamp((futures.confidence + options.confidence) / 2)
        if bias == "CONFLICTED":
            confidence = self._clamp(confidence - cfg.conflict_penalty)
        all_flags = tuple(dict.fromkeys((*flags, *futures.quality_flags, *options.quality_flags)))
        return PositioningIntelligence(
            futures, options, bias, confidence, dominant_state, all_flags,
            ("Evidence suggests positioning is developing; this result is informational only.",
             "Measured evidence is reported separately from interpretation."),
        )

    def _futures(self, context, cfg, shared_flags):
        volume = context.volume_structure
        price = self._number(getattr(volume, "price_change_percent", None))
        if price is None:
            intelligence = context.market_snapshot.intelligence or {}
            price_data = intelligence.get("price") if isinstance(intelligence, Mapping) else None
            price = self._first_number(price_data or intelligence, ("change_percent", "price_change_percent", "change_pct"))
        summary = context.market_snapshot.option_result.get("summary") or {}
        oi = self._first_number(summary, ("futures_oi_change_percent", "futures_oi_change", "future_oi_change"))
        proxy = False
        if oi is None:
            proxy = bool(summary.get("futures_oi_proxy"))
            if proxy:
                metrics = context.institutional_metrics
                if metrics is not None:
                    oi = self._number(metrics.oi.call_oi_change + metrics.oi.put_oi_change)
        flags = []
        evidence = []
        contradictions = []
        if price is None:
            flags.append("PRICE_DIRECTION_UNAVAILABLE")
        if oi is None:
            flags.extend(("OI_UNAVAILABLE", "OI_HISTORY_INSUFFICIENT"))
        if proxy:
            flags.append("FUTURES_OI_PROXY_ONLY")
        if price is None or oi is None:
            return self._state("UNAVAILABLE", 0, evidence, ("Validated price and futures OI are required.",), flags)
        pdir = 0 if abs(price) < cfg.price_neutral_threshold else 1 if price > 0 else -1
        odir = 0 if abs(oi) < max(cfg.oi_neutral_threshold, cfg.minimum_oi_change) else 1 if oi > 0 else -1
        evidence.extend((f"Underlying price change: {price:+.2f}%.", f"Futures OI change: {oi:+.2f}{' (explicit proxy)' if proxy else ''}."))
        if not pdir or not odir:
            contradictions.append("Price or OI is inside its configured neutral band.")
            return self._state("NEUTRAL", 25, evidence, contradictions, flags)
        state = {(1, 1): "LONG_BUILDUP", (-1, 1): "SHORT_BUILDUP", (1, -1): "SHORT_COVERING", (-1, -1): "LONG_UNWINDING"}[(pdir, odir)]
        confidence = cfg.price_oi_weight
        confirmation = getattr(volume, "volume_confirmation", "UNAVAILABLE")
        volume_strength = self._number(getattr(volume, "volume_strength", None))
        if confirmation == "CONFIRMED" and (volume_strength or 0) >= cfg.minimum_volume_confirmation:
            confidence += cfg.volume_weight
            evidence.append("Volume confirms the price move.")
        elif confirmation in {"DIVERGENT", "WEAK"}:
            confidence -= cfg.volume_weight
            contradictions.append("Volume diverges from the price move.")
        zone = getattr(context.market_location, "zone", "UNKNOWN")
        if (zone == "TOP" and state in {"LONG_BUILDUP", "SHORT_COVERING"}) or (zone == "BOTTOM" and state in {"SHORT_BUILDUP", "LONG_UNWINDING"}):
            confidence -= cfg.context_weight
            contradictions.append(f"{zone.title()} location creates climax or exhaustion risk.")
        if proxy:
            confidence = min(confidence, cfg.proxy_data_confidence_ceiling)
        return self._state(state, confidence, evidence, contradictions, flags)

    def _options(self, context, cfg, shared_flags):
        metrics = context.institutional_metrics
        if metrics is None:
            return self._state("UNAVAILABLE", 0, (), ("Institutional metrics are unavailable.",), ("OI_UNAVAILABLE",))
        raw = context.market_snapshot.option_result.get("chain")
        try:
            chain = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        except (TypeError, ValueError):
            chain = pd.DataFrame()
        if chain.empty:
            return self._state("UNAVAILABLE", 0, (), ("Option chain is missing or malformed.",), ("OI_UNAVAILABLE",))
        aliases = {"call_oi_change": ("call_oi_change", "ce_oi_change"), "put_oi_change": ("put_oi_change", "pe_oi_change"), "call_price_change": ("call_price_change", "ce_price_change"), "put_price_change": ("put_price_change", "pe_price_change")}
        totals = {}
        flags = []
        for key, names in aliases.items():
            name = next((n for n in names if n in chain), None)
            values = pd.to_numeric(chain[name], errors="coerce") if name else pd.Series(dtype=float)
            totals[key] = float(values.dropna().sum()) if not values.dropna().empty else None
        if totals["call_price_change"] is None or totals["put_price_change"] is None:
            flags.append("OPTION_PREMIUM_UNAVAILABLE")
        if metrics.volatility.atm_iv is None:
            flags.append("IV_UNAVAILABLE")
        if metrics.greeks.gamma is None:
            flags.append("GREEKS_UNAVAILABLE")
        if metrics.liquidity.thin_market or metrics.liquidity.liquidity_score < cfg.liquidity_minimum:
            flags.append("LIQUIDITY_THIN")
        candidates = []
        evidence = []
        contradictions = []
        for side in ("call", "put"):
            oi, premium = totals[f"{side}_oi_change"], totals[f"{side}_price_change"]
            writing_score = getattr(metrics.positioning, f"{side}_writing_score", 0)
            volume = getattr(metrics.liquidity, f"{side}_volume", 0)
            if oi is not None and oi >= cfg.minimum_oi_change and premium is not None:
                if premium <= -cfg.premium_change_threshold and writing_score >= cfg.writing_score_threshold:
                    candidates.append((f"{side.upper()}_WRITING", abs(oi) + writing_score))
                    evidence.append(f"{side.title()} OI rose while premium fell; writing score confirmed.")
                elif premium >= cfg.premium_change_threshold and volume >= cfg.buying_score_threshold:
                    candidates.append((f"{side.upper()}_BUYING", abs(oi) + volume))
                    evidence.append(f"{side.title()} volume and premium rose with OI demand.")
                else:
                    contradictions.append(f"{side.title()} OI increase lacks decisive premium confirmation.")
            elif oi is not None and oi >= cfg.minimum_oi_change:
                contradictions.append(f"{side.title()} OI rose, but premium confirmation is unavailable.")
        if not candidates:
            state = "NEUTRAL" if any(v is not None for v in totals.values()) else "UNAVAILABLE"
            confidence = min(20.0, cfg.missing_data_confidence_ceiling)
            return self._state(state, confidence, evidence, contradictions, flags)
        candidate_states = {item[0] for item in candidates}
        directions = {self._direction(item) for item in candidate_states}
        if len(candidate_states) > 1 and (len(directions) > 1 or any("BUYING" in x for x in candidate_states) and any("WRITING" in x for x in candidate_states)):
            flags.append("POSITIONING_CONFLICTED")
            return self._state("MIXED", 30, evidence, (*contradictions, "Multiple option behaviours have comparable evidence."), flags)
        state = max(candidates, key=lambda item: item[1])[0]
        confidence = cfg.price_oi_weight + cfg.premium_weight
        if "LIQUIDITY_THIN" not in flags:
            confidence += cfg.liquidity_weight
        else:
            confidence -= cfg.conflict_penalty
        if "OPTION_PREMIUM_UNAVAILABLE" in flags:
            confidence = min(confidence, cfg.missing_data_confidence_ceiling)
        zone = getattr(context.market_location, "zone", "UNKNOWN")
        if (state == "PUT_WRITING" and zone == "BOTTOM") or (state == "CALL_WRITING" and zone == "TOP"):
            confidence += cfg.context_weight
            evidence.append(f"{zone.title()} location is consistent with conditional {'support' if state == 'PUT_WRITING' else 'resistance' }.")
        return self._state(state, confidence, evidence, contradictions, flags)

    def _context_flags(self, context, cfg, flags):
        if context.market_location is None:
            flags.append("MARKET_LOCATION_UNAVAILABLE")
        if context.volume_structure is None:
            flags.append("VOLUME_STRUCTURE_UNAVAILABLE")
        stamp = (context.market_snapshot.timestamps or {}).get("last_refresh")
        if stamp:
            try:
                parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
                if (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() > cfg.stale_data_threshold:
                    flags.append("STALE_DATA")
            except (TypeError, ValueError):
                pass

    @staticmethod
    def _first_number(source, names):
        if not isinstance(source, Mapping):
            return None
        for name in names:
            value = PositioningIntelligenceEngine._number(source.get(name))
            if value is not None:
                return value
        return None

    @staticmethod
    def _number(value):
        try:
            number = float(value)
            return number if np.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _direction(state):
        if state in {"LONG_BUILDUP", "SHORT_COVERING", "PUT_WRITING", "CALL_BUYING"}:
            return "BULLISH"
        if state in {"SHORT_BUILDUP", "LONG_UNWINDING", "CALL_WRITING", "PUT_BUYING"}:
            return "BEARISH"
        return "NEUTRAL" if state in {"NEUTRAL", "MIXED"} else "UNKNOWN"

    @classmethod
    def _state(cls, state, confidence, evidence, contradictions, flags):
        meaning, impact = _DEFINITIONS[state]
        return PositioningState(state, meaning, impact, cls._clamp(confidence), tuple(evidence), tuple(contradictions), tuple(dict.fromkeys(flags)))

    @staticmethod
    def _clamp(value):
        return float(np.clip(value, 0.0, 100.0))
