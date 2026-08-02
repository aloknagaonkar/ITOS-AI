"""Deterministic, informational aggregation of institutional evidence."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from .decision_context import DecisionContext


@dataclass(frozen=True)
class EvidenceItem:
    code: str
    label: str
    direction: str
    strength: float
    reliability: float
    source: str
    explanation: str


@dataclass(frozen=True)
class InstitutionalEvidence:
    bias: str
    display_label: str
    meaning: str
    bullish_score: float
    bearish_score: float
    neutral_score: float
    evidence_quality: float
    confidence: float
    dominant_theme: str
    secondary_theme: str | None
    bullish_evidence: tuple[EvidenceItem, ...]
    bearish_evidence: tuple[EvidenceItem, ...]
    neutral_evidence: tuple[EvidenceItem, ...]
    contradictions: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]
    narrative: str


@dataclass(frozen=True)
class InstitutionalEvidenceSettings:
    source_weights: tuple[tuple[str, float], ...] = (("MarketLocation", .8), ("VolumeStructure", 1.15), ("PositioningIntelligence", 1.2), ("CompressionIntelligence", .75), ("ManipulationIntelligence", 1.0), ("InstitutionalMetrics", 1.0), ("InstitutionalFlow", 1.0), ("MarketRegime", .6))
    minimum_independent_groups: int = 3
    slight_threshold: float = 6.0
    directional_threshold: float = 18.0
    strong_threshold: float = 35.0
    strong_quality: float = 65.0
    conflicted_score: float = 45.0
    contradiction_penalty: float = 7.0
    missing_penalty: float = 5.0
    thin_liquidity_penalty: float = 15.0
    proxy_penalty: float = 12.0
    stale_penalty: float = 15.0
    low_quality_threshold: float = 40.0
    unavailable_confidence_ceiling: float = 30.0
    risk_confidence_ceiling: float = 55.0
    theme_priority: tuple[str, ...] = ("BULL_TRAP_RISK", "BEAR_TRAP_RISK", "ACCUMULATION", "DISTRIBUTION", "BULLISH_EXPANSION", "BEARISH_EXPANSION", "LONG_BUILDUP", "SHORT_BUILDUP", "PUT_WRITING_SUPPORT", "CALL_WRITING_RESISTANCE", "COMPRESSION_RELEASE", "COMPRESSION_BUILDING", "RANGE_BALANCE", "MIXED_POSITIONING")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "InstitutionalEvidenceSettings":
        raw = (value or {}).get("institutional_evidence", value or {})
        allowed = {f.name for f in fields(cls)}
        try:
            return cls(**{k: raw[k] for k in allowed if k in raw})
        except (TypeError, ValueError):
            return cls()


class InstitutionalEvidenceEngine:
    """Aggregate typed results without repositories, UI, or decision side effects."""
    def __init__(self, settings: InstitutionalEvidenceSettings | None = None):
        self.settings = settings

    def analyze(self, context: DecisionContext) -> InstitutionalEvidence:
        cfg = self.settings or InstitutionalEvidenceSettings.from_mapping(context.configuration or context.runtime_configuration)
        items: dict[str, EvidenceItem] = {}
        missing: list[str] = []
        flags: list[str] = []
        contradictions: list[str] = []
        themes: list[tuple[str, float]] = []
        def add(code, label, direction, strength, reliability, source, explanation, theme=None):
            if code not in items:
                items[code] = EvidenceItem(code, label, direction, self._clamp(strength), self._clamp(reliability), source, explanation)
                if theme: themes.append((theme, strength * reliability / 100))
        def unavailable(name, text):
            missing.append(text); flags.append(name.upper() + "_UNAVAILABLE")

        loc = context.market_location
        if loc is None or getattr(loc, "zone", "UNKNOWN") in {"UNKNOWN", "UNAVAILABLE"}: unavailable("MARKET_LOCATION", "Market location unavailable")
        else:
            zone, direction = str(loc.zone).upper(), str(getattr(loc, "direction", "NEUTRAL")).upper()
            if zone in {"BOTTOM", "LOWER_RANGE"} and direction in {"UP", "UPWARD", "BULLISH"}: add("LOCATION_LOWER_UP", "Lower-range upward transition", "BULLISH", 65, loc.confidence, "MarketLocation", "Price appears to be rotating upward from the lower active range.")
            elif zone in {"TOP", "UPPER_RANGE"} and direction in {"DOWN", "DOWNWARD", "BEARISH"}: add("LOCATION_UPPER_DOWN", "Upper-range downward transition", "BEARISH", 65, loc.confidence, "MarketLocation", "Price appears to be rotating downward from the upper active range.")
            elif zone in {"MIDDLE", "MID_RANGE", "BALANCED"}: add("LOCATION_BALANCED", "Balanced location", "NEUTRAL", 55, loc.confidence, "MarketLocation", "Price remains near the middle of its active range.", "RANGE_BALANCE")
        vol = context.volume_structure
        if vol is None or getattr(vol, "direction", "UNKNOWN") in {"UNKNOWN", "UNAVAILABLE"}: unavailable("VOLUME_STRUCTURE", "Price-volume behaviour unavailable")
        else:
            rel = getattr(vol, "confidence", 50)
            if getattr(vol, "accumulation_score", 0) >= 50: add("VOLUME_ACCUMULATION", "Possible accumulation", "BULLISH", vol.accumulation_score, rel, "VolumeStructure", "Location-aware price and volume evidence favours possible accumulation.", "ACCUMULATION")
            if getattr(vol, "distribution_score", 0) >= 50: add("VOLUME_DISTRIBUTION", "Possible distribution", "BEARISH", vol.distribution_score, rel, "VolumeStructure", "Location-aware price and volume evidence favours possible distribution.", "DISTRIBUTION")
            pdirection = str(getattr(vol, "price_direction", "FLAT"))
            confirm = str(getattr(vol, "volume_confirmation", "NEUTRAL"))
            if confirm == "CONFIRMED" and pdirection == "RISING": add("VOLUME_BULLISH_CONFIRMED", "Bullish price-volume confirmation", "BULLISH", vol.price_strength, rel, "VolumeStructure", "Rising price is confirmed by participation.", "BULLISH_EXPANSION")
            elif confirm == "CONFIRMED" and pdirection == "FALLING": add("VOLUME_BEARISH_CONFIRMED", "Bearish price-volume confirmation", "BEARISH", vol.price_strength, rel, "VolumeStructure", "Falling price is confirmed by participation.", "BEARISH_EXPANSION")
            elif pdirection == "FLAT": add("VOLUME_FLAT", "Flat price behaviour", "NEUTRAL", 45, rel, "VolumeStructure", "Price behaviour is currently flat.")
        pos = context.positioning_intelligence
        if pos is None or getattr(pos, "dominant_state", "UNAVAILABLE") == "UNAVAILABLE": unavailable("POSITIONING", "Positioning unavailable")
        else:
            state = str(pos.dominant_state).upper(); direction = {"LONG_BUILDUP":"BULLISH","SHORT_COVERING":"BULLISH","PUT_WRITING":"BULLISH","CALL_BUYING":"BULLISH","SHORT_BUILDUP":"BEARISH","LONG_UNWINDING":"BEARISH","CALL_WRITING":"BEARISH","PUT_BUYING":"BEARISH"}.get(state, "NEUTRAL")
            reliability = getattr(pos, "overall_confidence", 50) * ({"SHORT_COVERING":.72,"LONG_UNWINDING":.72,"CALL_BUYING":.75,"PUT_BUYING":.75}.get(state, 1))
            caveat = {"CALL_BUYING":"; call demand may also be hedging.","PUT_BUYING":"; put demand may also be protection.","SHORT_COVERING":" and may be less sustainable than fresh longs.","LONG_UNWINDING":" and is weaker than fresh short build-up."}.get(state, ".")
            theme = {"PUT_WRITING":"PUT_WRITING_SUPPORT","CALL_WRITING":"CALL_WRITING_RESISTANCE"}.get(state, state if state in cfg.theme_priority else "MIXED_POSITIONING")
            add("POSITIONING_"+state, state.replace("_", " ").title(), direction, getattr(pos, "overall_confidence", 50), reliability, "PositioningIntelligence", "Dominant positioning is " + state.replace("_", " ").lower() + caveat, theme)
        comp = context.compression_intelligence
        if comp is None or getattr(comp, "state", "UNAVAILABLE") == "UNAVAILABLE": unavailable("COMPRESSION", "Compression unavailable")
        else:
            state = str(comp.state).upper(); lean = str(getattr(comp, "direction", getattr(comp, "directional_lean", "NEUTRAL"))).upper()
            if "RELEAS" in state or "EXPAND" in state: add("COMPRESSION_RELEASE_"+lean, "Compression release", lean if lean in {"BULLISH","BEARISH"} else "NEUTRAL", comp.expansion_readiness, comp.confidence, "CompressionIntelligence", "Stored energy appears to be releasing; directional confirmation remains conditional.", "COMPRESSION_RELEASE")
            else: add("COMPRESSION_BUILDING", "Compression building", "NEUTRAL", comp.energy_stored, comp.confidence, "CompressionIntelligence", "Compression is building without confirmed direction.", "COMPRESSION_BUILDING")
        manip = context.manipulation_intelligence
        if manip is None or getattr(manip, "state", "UNAVAILABLE") == "UNAVAILABLE": unavailable("MANIPULATION", "Manipulation evidence unavailable")
        else:
            if getattr(manip, "false_breakdown_detected", False) or getattr(manip, "bear_trap_risk", 0) >= 65: add("MANIPULATION_BEAR_TRAP", "Bear-trap / false-breakdown risk", "BULLISH", max(manip.bear_trap_risk, manip.trap_severity), manip.confidence, "ManipulationIntelligence", "A failed downside move may support reversal, but confirmation remains conditional.", "BEAR_TRAP_RISK")
            if getattr(manip, "false_breakout_detected", False) or getattr(manip, "bull_trap_risk", 0) >= 65: add("MANIPULATION_BULL_TRAP", "Bull-trap / false-breakout risk", "BEARISH", max(manip.bull_trap_risk, manip.trap_severity), manip.confidence, "ManipulationIntelligence", "A failed upside move raises bull-trap risk.", "BULL_TRAP_RISK")
            if getattr(manip, "follow_through_quality", 100) < 35: contradictions.append("Directional evidence has insufficient follow-through.")
        metrics = context.institutional_metrics
        if metrics is None: unavailable("INSTITUTIONAL_METRICS", "Institutional metrics unavailable")
        else:
            pcr = getattr(getattr(metrics, "pcr", None), "weighted_pcr", None)
            if pcr is None: missing.append("PCR unavailable")
            elif .9 <= pcr <= 1.1: add("METRICS_BALANCED_PCR", "Balanced PCR", "NEUTRAL", 50, 70, "InstitutionalMetrics", "Weighted PCR is balanced.")
            elif pcr > 1.1: add("METRICS_SUPPORTIVE_PCR", "Supportive PCR", "BULLISH", min(100, pcr*45), 65, "InstitutionalMetrics", "Weighted PCR provides supportive options context.")
            else: add("METRICS_BEARISH_PCR", "Bearish PCR context", "BEARISH", min(100, (1.1-pcr)*80+45), 65, "InstitutionalMetrics", "Weighted PCR provides bearish options context.")
            liq = getattr(metrics, "liquidity", None)
            if liq is None: missing.append("Liquidity unavailable")
            elif getattr(liq, "thin_market", False): flags.append("LIQUIDITY_THIN")
            if getattr(getattr(metrics, "volatility", None), "atm_iv", None) is None: missing.append("IV unavailable")
            if getattr(getattr(metrics, "greeks", None), "gamma", None) is None: missing.append("Greeks unavailable")
            flags.extend("PROXY_EVIDENCE_PRESENT" for f in getattr(metrics, "quality_flags", ()) if "proxy" in str(f).lower())
        flow = context.flow_result
        meta = getattr(flow, "metadata", {}) if flow is not None else {}
        fdir = str(meta.get("direction", meta.get("flow", ""))).upper() if isinstance(meta, Mapping) else ""
        if not fdir or fdir in {"UNKNOWN", "UNAVAILABLE"}: unavailable("INSTITUTIONAL_FLOW", "Institutional flow unavailable")
        elif fdir in {"BULLISH","CE","UP"}: add("FLOW_BULLISH", "Bullish institutional flow", "BULLISH", meta.get("score", 60), meta.get("confidence", 60), "InstitutionalFlow", "Institutional flow aligns bullishly.")
        elif fdir in {"BEARISH","PE","DOWN"}: add("FLOW_BEARISH", "Bearish institutional flow", "BEARISH", meta.get("score", 60), meta.get("confidence", 60), "InstitutionalFlow", "Institutional flow aligns bearishly.")
        else: add("FLOW_NEUTRAL", "Neutral institutional flow", "NEUTRAL", 45, meta.get("confidence", 50), "InstitutionalFlow", "Institutional flow is mixed or weak.")
        all_items = tuple(items.values()); groups = len({i.source for i in all_items})
        if groups < cfg.minimum_independent_groups: flags.append("INDEPENDENT_EVIDENCE_INSUFFICIENT")
        bullish = self._score(all_items, "BULLISH", cfg); bearish = self._score(all_items, "BEARISH", cfg); neutral = self._score(all_items, "NEUTRAL", cfg)
        if bullish and bearish:
            contradictions.append("Bullish and bearish evidence remain simultaneously active.")
        quality = 85 - len(set(missing))*cfg.missing_penalty
        if "LIQUIDITY_THIN" in flags: quality -= cfg.thin_liquidity_penalty
        if "PROXY_EVIDENCE_PRESENT" in flags: quality -= cfg.proxy_penalty
        if any("STALE" in f for f in flags): quality -= cfg.stale_penalty
        quality = self._clamp(quality if all_items else 0)
        if quality < cfg.low_quality_threshold: flags.append("EVIDENCE_QUALITY_LOW")
        bias = self._bias(bullish, bearish, neutral, quality, len(contradictions), groups, cfg)
        if bias == "CONFLICTED": flags.append("EVIDENCE_CONFLICTED")
        separation = abs(bullish-bearish)
        confidence = self._clamp(quality*.65 + separation*.35 - len(contradictions)*cfg.contradiction_penalty - len(set(missing))*2)
        if "LIQUIDITY_THIN" in flags or "PROXY_EVIDENCE_PRESENT" in flags or contradictions: confidence = min(confidence, cfg.risk_confidence_ceiling)
        if "MANIPULATION_UNAVAILABLE" in flags or "POSITIONING_UNAVAILABLE" in flags: confidence = min(confidence, cfg.unavailable_confidence_ceiling)
        ranked = sorted(themes, key=lambda x: (-x[1], cfg.theme_priority.index(x[0]) if x[0] in cfg.theme_priority else 999, x[0]))
        dominant = ranked[0][0] if ranked else ("DATA_INSUFFICIENT" if not all_items else "RANGE_BALANCE")
        secondary = next((x[0] for x in ranked[1:] if x[0] != dominant), None)
        display = bias.replace("_", " ").title()
        meaning = "Available evidence favours " + display.lower() + " institutional context; confirmation remains conditional."
        narrative = self._narrative(loc, vol, pos, comp, manip, metrics, display, contradictions, missing)
        return InstitutionalEvidence(bias, display, meaning, bullish, bearish, neutral, quality, confidence, dominant, secondary,
            tuple(i for i in all_items if i.direction=="BULLISH"), tuple(i for i in all_items if i.direction=="BEARISH"), tuple(i for i in all_items if i.direction=="NEUTRAL"), tuple(dict.fromkeys(contradictions)), tuple(dict.fromkeys(missing)), tuple(dict.fromkeys(flags)), tuple(i.explanation for i in all_items), narrative)

    @staticmethod
    def _clamp(value):
        try: return round(max(0., min(100., float(value))), 2)
        except (TypeError, ValueError): return 0.
    def _score(self, items, direction, cfg):
        weights = dict(cfg.source_weights); selected = [i for i in items if i.direction == direction]
        numerator = sum(weights.get(i.source, .5)*i.strength*i.reliability/100 for i in selected)
        denominator = sum(weights.get(i.source, .5) for i in selected)
        return self._clamp(numerator/denominator if denominator else 0)
    @staticmethod
    def _bias(bull, bear, neutral, quality, conflicts, groups, cfg):
        if groups == 0 or quality <= 10: return "UNAVAILABLE"
        if (bull >= cfg.conflicted_score and bear >= cfg.conflicted_score) or conflicts >= 2: return "CONFLICTED"
        diff = bull-bear
        if abs(diff) < cfg.slight_threshold: return "NEUTRAL"
        side = "BULLISH" if diff > 0 else "BEARISH"
        if abs(diff) >= cfg.strong_threshold and quality >= cfg.strong_quality: return "STRONGLY_"+side
        if abs(diff) >= cfg.directional_threshold: return side
        return "SLIGHTLY_"+side
    @staticmethod
    def _narrative(loc, vol, pos, comp, manip, metrics, display, contradictions, missing):
        parts = [f"Location is {str(getattr(loc, 'zone', 'unavailable')).replace('_',' ').lower()}.", f"Price-volume behaviour is {str(getattr(vol, 'interpretation', 'unavailable')).replace('_',' ').lower()}.", f"Dominant positioning is {str(getattr(pos, 'dominant_state', 'unavailable')).replace('_',' ').lower()}.", f"Compression is {str(getattr(comp, 'state', 'unavailable')).replace('_',' ').lower()}.", f"Manipulation risk is {str(getattr(manip, 'risk_label', 'unavailable')).lower()}."]
        pcr = getattr(getattr(metrics, "pcr", None), "weighted_pcr", None)
        parts.append(f"The strongest metric context includes weighted PCR {pcr:.2f}." if isinstance(pcr, (int,float)) else "Institutional metric confirmation is incomplete.")
        parts.append(f"Overall evidence favours {display.lower()}, but remains informational and conditional.")
        if contradictions: parts.append("A contradiction remains: " + contradictions[0])
        if missing: parts.append("Missing confirmation: " + missing[0] + ".")
        return " ".join(parts)
