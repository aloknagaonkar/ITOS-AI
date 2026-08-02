"""Explainable, direction-neutral setup reliability intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from .decision_context import DecisionContext


def _clamp(value: Any) -> float:
    try:
        return round(max(0.0, min(100.0, float(value))), 4)
    except (TypeError, ValueError, OverflowError):
        return 0.0


@dataclass(frozen=True)
class ConfidencePillar:
    code: str
    label: str
    score: float
    weight: float
    reliability: float
    contribution: float
    explanation: str
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class DecisionConfidence:
    score: float
    grade: str
    setup_quality: str
    ranking_ready: bool
    market_context_score: float
    price_volume_score: float
    positioning_score: float
    compression_score: float
    manipulation_safety_score: float
    institutional_evidence_score: float
    data_quality_score: float
    pillars: tuple[ConfidencePillar, ...]
    contributors: tuple[str, ...]
    penalties: tuple[str, ...]
    missing_confirmations: tuple[str, ...]
    confidence_ceiling: float
    confidence_floor: float
    evidence_quality: float
    contradiction_count: int
    critical_blocker_count: int
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]
    narrative: str

    @property
    def primary_reason(self) -> str:
        return self.contributors[0] if self.contributors else "No strong confirmation is available."

    @property
    def primary_blocker(self) -> str:
        return self.penalties[0] if self.penalties else "None"


@dataclass(frozen=True)
class DecisionConfidenceSettings:
    pillar_weights: tuple[tuple[str, float], ...] = (
        ("MARKET_CONTEXT", 15), ("PRICE_VOLUME", 15), ("POSITIONING", 15),
        ("COMPRESSION", 10), ("MANIPULATION_SAFETY", 15),
        ("INSTITUTIONAL_EVIDENCE", 20), ("DATA_QUALITY", 10),
    )
    minimum_pillar_reliability: float = 10
    minimum_valid_pillars: int = 5
    ranking_ready_threshold: float = 70
    evidence_quality_minimum: float = 55
    data_quality_minimum: float = 60
    contradiction_maximum: int = 2
    critical_manipulation_threshold: float = 70
    critical_trap_severity_threshold: float = 70
    confidence_floor: float = 0
    thin_liquidity_penalty: float = 8
    stale_data_penalty: float = 20
    proxy_evidence_penalty: float = 7
    contradiction_penalty: float = 5
    mixed_positioning_penalty: float = 8
    volume_divergence_penalty: float = 7
    compression_conflict_penalty: float = 6
    missing_module_penalty: float = 5
    manipulation_unavailable_ceiling: float = 70
    evidence_unavailable_ceiling: float = 55
    positioning_unavailable_ceiling: float = 65
    stale_data_ceiling: float = 50
    critical_candles_ceiling: float = 35
    proxy_evidence_ceiling: float = 75
    thin_incomplete_ceiling: float = 60
    grade_thresholds: tuple[tuple[float, str], ...] = ((95, "A_PLUS"), (85, "A"), (70, "B"), (55, "C"), (40, "D"), (0, "AVOID"))
    setup_quality_thresholds: tuple[tuple[float, str], ...] = ((95, "INSTITUTIONAL_GRADE"), (85, "HIGH_QUALITY"), (70, "TRADABLE"), (55, "DEVELOPING"), (40, "WEAK"), (0, "AVOID"))
    penalty_deduplication_priority: tuple[str, ...] = ("STALE_DATA", "CRITICAL_CANDLES_MISSING", "MANIPULATION_RISK", "TRAP_SEVERITY", "CONTRADICTIONS", "THIN_LIQUIDITY", "PROXY_EVIDENCE", "MIXED_POSITIONING", "VOLUME_DIVERGENCE", "COMPRESSION_CONFLICT", "MISSING_MODULE")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "DecisionConfidenceSettings":
        raw = (value or {}).get("decision_confidence", value or {})
        allowed = {item.name for item in fields(cls)}
        try:
            return cls(**{key: raw[key] for key in allowed if key in raw})
        except (TypeError, ValueError):
            return cls()


class DecisionConfidenceEngine:
    """Aggregate completed typed intelligence without affecting recommendations."""

    def __init__(self, settings: DecisionConfidenceSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, context: DecisionContext) -> DecisionConfidence:
        cfg = self.settings or DecisionConfidenceSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        weights = dict(cfg.pillar_weights)
        weight_total = sum(max(0.0, float(v)) for v in weights.values()) or 100.0
        weights = {k: _clamp(float(v) * 100 / weight_total) for k, v in weights.items()}
        flags: list[str] = []
        contributors: list[str] = []
        missing: list[str] = []
        penalties: dict[str, tuple[str, float]] = {}
        ceilings = [100.0]
        blockers: set[str] = set()

        def add_penalty(code: str, text: str, impact: float) -> None:
            # One code represents one underlying fact; repeat observations do not stack.
            penalties.setdefault(code, (f"{code}: {text} (-{impact:g})", impact))

        def unavailable(code: str, text: str, ceiling: float | None = None) -> tuple[float, float, tuple[str, ...]]:
            flag = f"{code}_UNAVAILABLE"
            flags.append(flag); missing.append(text)
            add_penalty("MISSING_MODULE", "One or more required intelligence modules are unavailable", cfg.missing_module_penalty)
            if ceiling is not None: ceilings.append(ceiling)
            return 0.0, 0.0, (flag,)

        location = context.market_location
        if location is None or getattr(location, "zone", "UNKNOWN") in {"UNKNOWN", "UNAVAILABLE"}:
            market = unavailable("MARKET_CONTEXT", "Market location is unclear")
        else:
            score = _clamp(getattr(location, "confidence", 0))
            pflags = tuple(getattr(location, "quality_flags", ()) or ())
            if "STALE_DATA" in pflags: score -= 20
            market = (_clamp(score), _clamp(getattr(location, "confidence", 0)), pflags)
            if score >= 70: contributors.append("Market location and transition are clear.")

        volume = context.volume_structure
        if volume is None or getattr(volume, "volume_confirmation", "UNAVAILABLE") == "UNAVAILABLE":
            pv = unavailable("PRICE_VOLUME", "Volume confirmation is missing")
        else:
            state = str(getattr(volume, "volume_confirmation", ""))
            score = _clamp(getattr(volume, "confidence", 0))
            if state in {"DIVERGENCE", "DIVERGING", "CONTRADICTED"}:
                score -= cfg.volume_divergence_penalty
                add_penalty("VOLUME_DIVERGENCE", "Price and volume diverge", cfg.volume_divergence_penalty)
                missing.append("Price-volume confirmation is unresolved")
            elif state in {"CONFIRMED", "ALIGNED", "CONFIRMING"}:
                contributors.append("Price and volume are aligned.")
            pv = (_clamp(score), _clamp(getattr(volume, "confidence", 0)), tuple(getattr(volume, "quality_flags", ()) or ()))

        positioning = context.positioning_intelligence
        if positioning is None or getattr(positioning, "dominant_state", "UNAVAILABLE") == "UNAVAILABLE":
            pos = unavailable("POSITIONING", "Positioning intelligence is unavailable", cfg.positioning_unavailable_ceiling)
        else:
            score = _clamp(getattr(positioning, "overall_confidence", 0))
            state = str(getattr(positioning, "dominant_state", ""))
            if state in {"MIXED", "CONFLICTED"}:
                score -= cfg.mixed_positioning_penalty
                add_penalty("MIXED_POSITIONING", "Futures and options positioning are mixed", cfg.mixed_positioning_penalty)
                missing.append("Positioning agreement is needed")
            elif score >= 65: contributors.append("Futures and options positioning are coherent.")
            pflags = tuple(getattr(positioning, "quality_flags", ()) or ())
            pos = (_clamp(score), _clamp(score), pflags)

        compression = context.compression_intelligence
        if compression is None or getattr(compression, "state", "UNAVAILABLE") == "UNAVAILABLE":
            comp = unavailable("COMPRESSION", "Compression state is unavailable")
        else:
            score = _clamp(getattr(compression, "confidence", 0))
            state = str(getattr(compression, "state", ""))
            if state in {"CONFLICTED", "MIXED", "UNRESOLVED"}:
                score -= cfg.compression_conflict_penalty
                add_penalty("COMPRESSION_CONFLICT", "Compression components conflict", cfg.compression_conflict_penalty)
                missing.append("Compression release is unconfirmed")
            elif score >= 65: contributors.append("Compression state is well defined.")
            comp = (_clamp(score), _clamp(getattr(compression, "confidence", 0)), tuple(getattr(compression, "quality_flags", ()) or ()))

        manipulation = context.manipulation_intelligence
        if manipulation is None or getattr(manipulation, "state", "UNAVAILABLE") == "UNAVAILABLE":
            manip = unavailable("MANIPULATION", "Manipulation analysis is unavailable", cfg.manipulation_unavailable_ceiling)
        else:
            risk = _clamp(getattr(manipulation, "manipulation_probability", 0))
            trap = _clamp(getattr(manipulation, "trap_severity", 0))
            score = _clamp(100 - max(risk, trap))
            reliability = _clamp(getattr(manipulation, "confidence", 0))
            if risk >= cfg.critical_manipulation_threshold:
                blockers.add("MANIPULATION_RISK"); add_penalty("MANIPULATION_RISK", "Manipulation risk is elevated", risk / 10)
            if trap >= cfg.critical_trap_severity_threshold:
                blockers.add("TRAP_SEVERITY"); add_penalty("TRAP_SEVERITY", "Trap severity is elevated", trap / 10)
            if score >= 70: contributors.append("Manipulation risk is low.")
            manip = (score, reliability, tuple(getattr(manipulation, "quality_flags", ()) or ()))

        evidence = context.institutional_evidence
        contradiction_count = len(tuple(getattr(evidence, "contradictions", ()) or ())) if evidence else 0
        evidence_quality = _clamp(getattr(evidence, "evidence_quality", 0)) if evidence else 0.0
        if evidence is None or getattr(evidence, "bias", "UNAVAILABLE") == "UNAVAILABLE":
            inst = unavailable("INSTITUTIONAL_EVIDENCE", "Institutional evidence is unavailable", cfg.evidence_unavailable_ceiling)
            blockers.add("INSTITUTIONAL_EVIDENCE_UNAVAILABLE")
        else:
            score = (_clamp(getattr(evidence, "confidence", 0)) + evidence_quality) / 2
            if getattr(evidence, "bias", "") == "CONFLICTED": score -= 10
            if contradiction_count:
                impact = contradiction_count * cfg.contradiction_penalty
                score -= impact; add_penalty("CONTRADICTIONS", f"{contradiction_count} institutional contradiction(s) remain", impact)
            if contradiction_count > cfg.contradiction_maximum:
                flags.append("CONTRADICTIONS_HIGH"); blockers.add("CONTRADICTIONS_HIGH")
            if evidence_quality < cfg.evidence_quality_minimum:
                blockers.add("EVIDENCE_QUALITY_LOW"); missing.append("Institutional evidence quality is below the ranking minimum")
            elif score >= 70: contributors.append("Institutional evidence is high quality and independently supported.")
            inst = (_clamp(score), evidence_quality, tuple(getattr(evidence, "quality_flags", ()) or ()))

        health = context.engine_results.get("data_health")
        metadata = getattr(health, "metadata", {}) if health is not None else {}
        health_flags = tuple(metadata.get("flags", ()) or ()) if isinstance(metadata, Mapping) else ()
        if health is None:
            data = unavailable("DATA_QUALITY", "Data-health analysis is unavailable")
        else:
            score = _clamp(getattr(health, "score", 0))
            all_upstream_flags = set(health_flags)
            for item in (market[2], pv[2], pos[2], comp[2], manip[2], inst[2]): all_upstream_flags.update(item)
            stale = bool(all_upstream_flags & {"DATA_STALE", "STALE_DATA"})
            candles_missing = bool(all_upstream_flags & {"CANDLES_UNAVAILABLE", "CANDLES_MISSING", "OHLC_INVALID"})
            thin = bool(all_upstream_flags & {"OPTION_CHAIN_THIN", "LIQUIDITY_THIN", "THIN_LIQUIDITY"})
            proxy = any("PROXY" in str(flag) for flag in all_upstream_flags)
            if stale:
                flags.append("STALE_DATA"); blockers.add("STALE_DATA"); ceilings.append(cfg.stale_data_ceiling)
                add_penalty("STALE_DATA", "Market data is stale", cfg.stale_data_penalty); score -= cfg.stale_data_penalty
            if candles_missing:
                flags.append("CRITICAL_CANDLES_MISSING"); blockers.add("CRITICAL_CANDLES_MISSING"); ceilings.append(cfg.critical_candles_ceiling)
                add_penalty("CRITICAL_CANDLES_MISSING", "Critical candle data is missing", cfg.stale_data_penalty)
            if thin:
                flags.append("LIQUIDITY_THIN"); add_penalty("THIN_LIQUIDITY", "Liquidity is thin", cfg.thin_liquidity_penalty); score -= cfg.thin_liquidity_penalty
            if proxy:
                flags.append("PROXY_EVIDENCE_PRESENT"); ceilings.append(cfg.proxy_evidence_ceiling)
                add_penalty("PROXY_EVIDENCE", "Proxy evidence reduces reliability", cfg.proxy_evidence_penalty); score -= cfg.proxy_evidence_penalty
            if score >= 75: contributors.append("Liquidity and data quality are healthy.")
            if score < cfg.data_quality_minimum: blockers.add("DATA_QUALITY_LOW")
            data = (_clamp(score), _clamp(score), health_flags)

        specs = (
            ("MARKET_CONTEXT", "Market Context", market), ("PRICE_VOLUME", "Price & Volume", pv),
            ("POSITIONING", "Positioning", pos), ("COMPRESSION", "Compression", comp),
            ("MANIPULATION_SAFETY", "Manipulation Safety", manip),
            ("INSTITUTIONAL_EVIDENCE", "Institutional Evidence", inst), ("DATA_QUALITY", "Data Quality", data),
        )
        pillars = tuple(ConfidencePillar(code, label, _clamp(v[0]), weights.get(code, 0), _clamp(v[1]),
            _clamp(v[0] * v[1] * weights.get(code, 0) / 10000),
            f"{label} clarity is {_clamp(v[0]):.1f}/100 with {_clamp(v[1]):.1f}% reliability.", tuple(dict.fromkeys(v[2]))) for code, label, v in specs)
        valid = [p for p in pillars if p.reliability >= cfg.minimum_pillar_reliability]
        if not valid:
            flags.extend(("PILLARS_INSUFFICIENT", "DECISION_CONFIDENCE_UNAVAILABLE", "RANKING_NOT_READY"))
            return DecisionConfidence(0, "UNAVAILABLE", "UNAVAILABLE", False, *(p.score for p in pillars), pillars,
                tuple(contributors), tuple(v[0] for v in penalties.values()), tuple(dict.fromkeys(missing)),
                min(ceilings), _clamp(cfg.confidence_floor), evidence_quality, contradiction_count, len(blockers),
                tuple(dict.fromkeys(flags)), ("No reliable confidence pillars are available.",),
                "Decision confidence is unavailable. The setup is not ready for option ranking.")
        if len(valid) < cfg.minimum_valid_pillars: flags.append("PILLARS_INSUFFICIENT"); blockers.add("PILLARS_INSUFFICIENT")
        raw = sum(p.contribution for p in pillars)
        raw -= sum(value[1] for value in penalties.values())
        ceiling = _clamp(min(ceilings)); floor = _clamp(cfg.confidence_floor)
        score = _clamp(min(ceiling, max(floor, raw)))
        grade = self._band(score, cfg.grade_thresholds); quality = self._band(score, cfg.setup_quality_thresholds)
        ready = score >= cfg.ranking_ready_threshold and len(valid) >= cfg.minimum_valid_pillars and not blockers and contradiction_count <= cfg.contradiction_maximum and evidence_quality >= cfg.evidence_quality_minimum
        if blockers: flags.append("CRITICAL_BLOCKER_PRESENT")
        if not ready: flags.append("RANKING_NOT_READY")
        strongest = max(pillars, key=lambda p: p.score); weakest = min(pillars, key=lambda p: p.score)
        primary_penalty = next(iter(penalties.values()))[0] if penalties else "No major penalty is present."
        primary_missing = missing[0] if missing else "No material confirmation is missing."
        readiness = "eligible for future option ranking" if ready else "not ready for option ranking"
        narrative = (f"Decision confidence is {quality.replace('_', ' ').lower()}. The strongest pillar is {strongest.label} "
            f"({strongest.score:.1f}), while the weakest is {weakest.label} ({weakest.score:.1f}). {primary_penalty} "
            f"Missing confirmation: {primary_missing}. The setup is {readiness}; this assessment is informational only.")
        return DecisionConfidence(score, grade, quality, ready, *(p.score for p in pillars), pillars,
            tuple(dict.fromkeys(contributors)), tuple(value[0] for value in penalties.values()), tuple(dict.fromkeys(missing)),
            ceiling, floor, evidence_quality, contradiction_count, len(blockers), tuple(dict.fromkeys(flags)),
            (f"Strongest pillar: {strongest.label}.", f"Weakest pillar: {weakest.label}.", primary_penalty, primary_missing), narrative)

    @staticmethod
    def _band(score: float, thresholds: tuple[tuple[float, str], ...]) -> str:
        for minimum, label in sorted(thresholds, reverse=True):
            if score >= minimum: return label
        return thresholds[-1][1]
