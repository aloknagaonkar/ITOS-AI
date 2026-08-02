"""Deterministic, shadow-only validation of point-in-time decision confidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from math import sqrt
import re
from typing import Any

from .decision_confidence import DecisionConfidence
from .decision_context import DecisionContext


def _clamp(value: Any) -> float:
    try:
        return round(max(0.0, min(100.0, float(value))), 4)
    except (TypeError, ValueError, OverflowError):
        return 0.0


@dataclass(frozen=True)
class ConfidenceHistoryPoint:
    timestamp: object | None
    score: float
    grade: str
    setup_quality: str
    ranking_ready: bool
    pillar_scores: tuple[tuple[str, float], ...]
    penalties: tuple[str, ...]
    critical_blockers: tuple[str, ...]
    contradiction_count: int
    evidence_quality: float


@dataclass(frozen=True)
class DecisionConfidenceValidation:
    current_score: float
    previous_score: float | None
    score_change: float | None
    trend: str
    stability_state: str
    stability_score: float
    pillar_agreement_score: float
    ranking_ready_now: bool
    readiness_persistence: float
    ranking_eligible: bool
    ranking_eligibility_state: str
    valid_history_points: int
    improving_periods: int
    weakening_periods: int
    stable_periods: int
    strongest_improving_pillar: str | None
    weakest_deteriorating_pillar: str | None
    positive_change_drivers: tuple[str, ...]
    negative_change_drivers: tuple[str, ...]
    new_penalties: tuple[str, ...]
    resolved_penalties: tuple[str, ...]
    new_blockers: tuple[str, ...]
    resolved_blockers: tuple[str, ...]
    recommendation_alignment: str
    shadow_observation: str
    confidence: float
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]
    narrative: str

    @property
    def primary_change_driver(self) -> str:
        return next(iter(self.positive_change_drivers or self.negative_change_drivers), "No material change identified.")


@dataclass(frozen=True)
class DecisionConfidenceValidationSettings:
    trend_lookback: int = 6
    minimum_history_points: int = 3
    trend_slope_threshold: float = 1.5
    stable_slope_band: float = 1.0
    interval_neutral_band: float = 1.0
    volatility_threshold: float = 12.0
    stability_very_stable: float = 90.0
    stability_stable: float = 75.0
    stability_moderate: float = 55.0
    stability_unstable: float = 30.0
    pillar_quality_threshold: float = 60.0
    pillar_outlier_threshold: float = 30.0
    readiness_persistence_threshold: float = 80.0
    ranking_eligibility_score_threshold: float = 70.0
    ranking_eligibility_stability_minimum: float = 75.0
    ranking_eligibility_pillar_agreement_minimum: float = 70.0
    ranking_eligibility_evidence_quality_minimum: float = 55.0
    maximum_blocker_count: int = 0
    maximum_contradiction_count: int = 2
    significant_pillar_change_threshold: float = 4.0
    stale_history_hours: float = 24.0
    short_history_confidence_ceiling: float = 55.0
    missing_timestamp_confidence_ceiling: float = 65.0
    incomplete_pillars_confidence_ceiling: float = 70.0
    recent_point_weighting: float = 1.0

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "DecisionConfidenceValidationSettings":
        raw = (value or {}).get("decision_confidence_validation", value or {})
        allowed = {item.name for item in fields(cls)}
        try:
            return cls(**{key: raw[key] for key in allowed if key in raw})
        except (TypeError, ValueError):
            return cls()


class DecisionConfidenceValidationEngine:
    """Validate confidence history without changing any trading decision."""

    def __init__(self, settings: DecisionConfidenceValidationSettings | None = None) -> None:
        self.settings = settings

    def analyze(
        self, context: DecisionContext,
        history: Sequence[Any] | Any | None = None,
    ) -> DecisionConfidenceValidation:
        cfg = self.settings or DecisionConfidenceValidationSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        current = context.decision_confidence
        if current is None or getattr(current, "grade", "UNAVAILABLE") == "UNAVAILABLE":
            return self._unavailable()
        flags: list[str] = []
        raw_history = context.confidence_history if history is None else history
        rows = self._history_rows(raw_history)
        if raw_history is None or not rows:
            flags.append("HISTORY_UNAVAILABLE")
        normalized: list[ConfidenceHistoryPoint] = []
        invalid = 0
        timestamps_missing = False
        seen_timestamps: set[str] = set()
        duplicates = False
        for row in rows:
            point = self._normalize(row)
            if point is None:
                invalid += 1
                continue
            if point.timestamp is None:
                timestamps_missing = True
            else:
                key = self._timestamp_key(point.timestamp)
                if key in seen_timestamps:
                    duplicates = True
                    continue
                seen_timestamps.add(key)
            normalized.append(point)
        if invalid:
            flags.append("HISTORY_PARTIALLY_INVALID")
        if timestamps_missing:
            flags.append("TIMESTAMPS_UNAVAILABLE")
        if duplicates:
            flags.append("DUPLICATE_HISTORY_POINTS")
        if normalized and all(item.timestamp is not None for item in normalized):
            normalized.sort(key=lambda item: self._timestamp_key(item.timestamp))
        previous = normalized[-1] if normalized else None
        current_point = self._from_current(current, context.market_snapshot.timestamps.get("last_refresh"))
        points = (normalized + [current_point])[-max(2, cfg.trend_lookback):]
        valid_count = len(points)
        if valid_count < cfg.minimum_history_points:
            flags.append("HISTORY_INSUFFICIENT")
        if not any(point.pillar_scores for point in normalized):
            flags.append("PILLAR_HISTORY_UNAVAILABLE")
        if normalized and all(not point.penalties for point in normalized):
            flags.append("PENALTY_HISTORY_UNAVAILABLE")
        if normalized and all(not point.critical_blockers for point in normalized):
            flags.append("BLOCKER_HISTORY_UNAVAILABLE")
        if self._is_stale(previous, cfg.stale_history_hours):
            flags.append("HISTORY_STALE")

        scores = [point.score for point in points]
        changes = [right - left for left, right in zip(scores, scores[1:])]
        improving = sum(change > cfg.interval_neutral_band for change in changes)
        weakening = sum(change < -cfg.interval_neutral_band for change in changes)
        stable_periods = len(changes) - improving - weakening
        stability = self._stability(points, cfg)
        stability_state = self._stability_state(stability, valid_count, cfg)
        trend = self._trend(scores, changes, valid_count, cfg)
        agreement = self._pillar_agreement(current_point, cfg)
        weights = [1.0 + index * max(0.0, cfg.recent_point_weighting) for index in range(valid_count)]
        persistence = _clamp(sum(weight for weight, point in zip(weights, points) if point.ranking_ready) * 100 / sum(weights))

        change_data = self._changes(previous, current_point, cfg)
        positive, negative, new_penalties, resolved_penalties, new_blockers, resolved_blockers, strongest, weakest = change_data
        blockers = current_point.critical_blockers
        enough_history = valid_count >= cfg.minimum_history_points
        basic_pass = (
            current.ranking_ready
            and current.score >= cfg.ranking_eligibility_score_threshold
            and agreement >= cfg.ranking_eligibility_pillar_agreement_minimum
            and current.evidence_quality >= cfg.ranking_eligibility_evidence_quality_minimum
            and current.contradiction_count <= cfg.maximum_contradiction_count
            and len(blockers) <= cfg.maximum_blocker_count
            and not new_blockers
        )
        eligible = basic_pass and enough_history and stability >= cfg.ranking_eligibility_stability_minimum and persistence >= cfg.readiness_persistence_threshold
        if eligible:
            eligibility_state = "ELIGIBLE"
        elif not enough_history and basic_pass:
            eligibility_state = "INSUFFICIENT_HISTORY"
        elif basic_pass:
            eligibility_state = "CONDITIONALLY_ELIGIBLE"
        else:
            eligibility_state = "NOT_ELIGIBLE"
        if not eligible:
            flags.append("RANKING_NOT_ELIGIBLE")

        alignment, observation, alignment_flags = self._alignment(context, current, eligible)
        flags.extend(alignment_flags)
        confidence = min(100.0, 25.0 + min(valid_count, 6) * 10.0)
        if valid_count < cfg.minimum_history_points:
            confidence = min(confidence, cfg.short_history_confidence_ceiling)
        if timestamps_missing or current_point.timestamp is None:
            confidence = min(confidence, cfg.missing_timestamp_confidence_ceiling)
        if "PILLAR_HISTORY_UNAVAILABLE" in flags:
            confidence = min(confidence, cfg.incomplete_pillars_confidence_ceiling)
        if invalid or "HISTORY_STALE" in flags:
            confidence -= 10
        confidence = _clamp(confidence)
        if confidence < 50:
            flags.append("VALIDATION_CONFIDENCE_LOW")
        explanations = self._explanations(trend, stability_state, agreement, persistence, eligibility_state, new_blockers)
        narrative = self._narrative(trend, stability_state, agreement, strongest, weakest, new_blockers, eligibility_state, enough_history)
        return DecisionConfidenceValidation(
            _clamp(current.score), previous.score if previous else None,
            round(current.score - previous.score, 4) if previous else None,
            trend, stability_state, stability, agreement, bool(current.ranking_ready),
            persistence, eligible, eligibility_state, valid_count, improving, weakening,
            stable_periods, strongest, weakest, tuple(positive), tuple(negative),
            tuple(new_penalties), tuple(resolved_penalties), tuple(new_blockers),
            tuple(resolved_blockers), alignment, observation, confidence,
            tuple(dict.fromkeys(flags)), explanations, narrative,
        )

    @staticmethod
    def _history_rows(history: Any) -> list[Any]:
        if history is None:
            return []
        if hasattr(history, "to_dict"):
            try:
                return list(history.to_dict("records"))
            except (TypeError, ValueError):
                return []
        if isinstance(history, Mapping):
            return [history]
        if isinstance(history, Sequence) and not isinstance(history, (str, bytes)):
            return list(history)
        return []

    @classmethod
    def _normalize(cls, value: Any) -> ConfidenceHistoryPoint | None:
        getter = value.get if isinstance(value, Mapping) else lambda key, default=None: getattr(value, key, default)
        score = getter("score", getter("decision_confidence_score", None))
        try:
            score = float(score)
        except (TypeError, ValueError, OverflowError):
            return None
        if score != score:
            return None
        ranking = getter("ranking_ready", False)
        if not isinstance(ranking, bool):
            ranking = str(ranking).strip().lower() in {"true", "1", "yes"}
        pillars = getter("pillar_scores", ())
        if isinstance(pillars, Mapping):
            pillars = pillars.items()
        try:
            normalized_pillars = tuple((str(k), _clamp(v)) for k, v in pillars)
        except (TypeError, ValueError):
            normalized_pillars = ()
        return ConfidenceHistoryPoint(
            getter("timestamp", getter("created_at", None)), _clamp(score),
            str(getter("grade", "UNKNOWN")), str(getter("setup_quality", "UNKNOWN")),
            ranking, normalized_pillars, cls._texts(getter("penalties", ())),
            cls._texts(getter("critical_blockers", getter("blockers", ()))),
            max(0, cls._integer(getter("contradiction_count", 0))),
            _clamp(getter("evidence_quality", 0)),
        )

    @classmethod
    def _from_current(cls, current: DecisionConfidence, timestamp: Any) -> ConfidenceHistoryPoint:
        critical = tuple(flag for flag in current.quality_flags if flag in {
            "STALE_DATA", "CRITICAL_CANDLES_MISSING", "CONTRADICTIONS_HIGH",
            "INSTITUTIONAL_EVIDENCE_UNAVAILABLE", "DATA_QUALITY_LOW",
        })
        critical += tuple(item.split(":", 1)[0] for item in current.penalties if item.split(":", 1)[0] in {"MANIPULATION_RISK", "TRAP_SEVERITY"})
        return ConfidenceHistoryPoint(timestamp, _clamp(current.score), current.grade,
            current.setup_quality, current.ranking_ready,
            tuple((pillar.code, _clamp(pillar.score)) for pillar in current.pillars),
            cls._texts(current.penalties), tuple(dict.fromkeys(critical)),
            current.contradiction_count, _clamp(current.evidence_quality))

    @staticmethod
    def _texts(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, Sequence):
            return ()
        return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _timestamp_key(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value).strip()

    @staticmethod
    def _is_stale(point: ConfidenceHistoryPoint | None, hours: float) -> bool:
        if point is None or point.timestamp is None:
            return False
        try:
            parsed = point.timestamp if isinstance(point.timestamp, datetime) else datetime.fromisoformat(str(point.timestamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - parsed).total_seconds() > hours * 3600
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _stability(points: list[ConfidenceHistoryPoint], cfg: DecisionConfidenceValidationSettings) -> float:
        if len(points) < 2:
            return 0.0
        scores = [point.score for point in points]
        mean = sum(scores) / len(scores)
        deviation = sqrt(sum((score - mean) ** 2 for score in scores) / len(scores))
        maximum_change = max(abs(b - a) for a, b in zip(scores, scores[1:]))
        grade_changes = sum(a.grade != b.grade for a, b in zip(points, points[1:]))
        readiness_changes = sum(a.ranking_ready != b.ranking_ready for a, b in zip(points, points[1:]))
        penalty_changes = sum({DecisionConfidenceValidationEngine._canonical(x) for x in a.penalties} != {DecisionConfidenceValidationEngine._canonical(x) for x in b.penalties} for a, b in zip(points, points[1:]))
        blocker_changes = sum({DecisionConfidenceValidationEngine._canonical(x) for x in a.critical_blockers} != {DecisionConfidenceValidationEngine._canonical(x) for x in b.critical_blockers} for a, b in zip(points, points[1:]))
        intervals = max(1, len(points) - 1)
        penalty = deviation * 2.2 + maximum_change * 1.2 + grade_changes * 5 + readiness_changes * 8 + (penalty_changes + blocker_changes) * 3 / intervals
        return _clamp(100 - penalty)

    @staticmethod
    def _stability_state(score: float, count: int, cfg: DecisionConfidenceValidationSettings) -> str:
        if count < 2: return "INSUFFICIENT_HISTORY"
        if score >= cfg.stability_very_stable: return "VERY_STABLE"
        if score >= cfg.stability_stable: return "STABLE"
        if score >= cfg.stability_moderate: return "MODERATE"
        if score >= cfg.stability_unstable: return "UNSTABLE"
        return "HIGHLY_UNSTABLE"

    @staticmethod
    def _trend(scores: list[float], changes: list[float], count: int, cfg: DecisionConfidenceValidationSettings) -> str:
        if count < cfg.minimum_history_points: return "INSUFFICIENT_HISTORY"
        slope = (scores[-1] - scores[0]) / max(1, len(scores) - 1)
        alternating = sum(a * b < 0 for a, b in zip(changes, changes[1:]))
        if max((abs(x) for x in changes), default=0) >= cfg.volatility_threshold and alternating >= 1: return "VOLATILE"
        if slope >= cfg.trend_slope_threshold and sum(x > cfg.interval_neutral_band for x in changes) > len(changes) / 2: return "IMPROVING"
        if slope <= -cfg.trend_slope_threshold and sum(x < -cfg.interval_neutral_band for x in changes) > len(changes) / 2: return "WEAKENING"
        return "STABLE"

    @staticmethod
    def _pillar_agreement(point: ConfidenceHistoryPoint, cfg: DecisionConfidenceValidationSettings) -> float:
        values = [score for _, score in point.pillar_scores]
        if not values: return 0.0
        mean = sum(values) / len(values)
        deviation = sqrt(sum((score - mean) ** 2 for score in values) / len(values))
        quality_ratio = sum(score >= cfg.pillar_quality_threshold for score in values) / len(values)
        weak_penalty = max(0.0, cfg.pillar_quality_threshold - min(values)) * 0.5
        outlier_penalty = 15 if max(values) - min(values) >= cfg.pillar_outlier_threshold else 0
        completeness = min(1.0, len(values) / 7)
        return _clamp((100 - deviation * 1.8 - weak_penalty - outlier_penalty) * (0.5 + completeness * 0.5) * (0.65 + quality_ratio * 0.35))

    @classmethod
    def _changes(cls, previous: ConfidenceHistoryPoint | None, current: ConfidenceHistoryPoint, cfg: DecisionConfidenceValidationSettings) -> tuple:
        if previous is None:
            return [], [], [], [], [], [], None, None
        before, now = dict(previous.pillar_scores), dict(current.pillar_scores)
        deltas = {key: now[key] - before[key] for key in now.keys() & before.keys()}
        positive = [f"{key.replace('_', ' ').title()} improved ({delta:+.1f})." for key, delta in deltas.items() if delta >= cfg.significant_pillar_change_threshold]
        negative = [f"{key.replace('_', ' ').title()} weakened ({delta:+.1f})." for key, delta in deltas.items() if delta <= -cfg.significant_pillar_change_threshold]
        strongest = max((key for key in deltas if deltas[key] >= cfg.significant_pillar_change_threshold), key=deltas.get, default=None)
        weakest = min((key for key in deltas if deltas[key] <= -cfg.significant_pillar_change_threshold), key=deltas.get, default=None)
        p_before, p_now = cls._canonical_map(previous.penalties), cls._canonical_map(current.penalties)
        b_before, b_now = cls._canonical_map(previous.critical_blockers), cls._canonical_map(current.critical_blockers)
        new_p, resolved_p = [p_now[k] for k in p_now.keys() - p_before.keys()], [p_before[k] for k in p_before.keys() - p_now.keys()]
        new_b, resolved_b = [b_now[k] for k in b_now.keys() - b_before.keys()], [b_before[k] for k in b_before.keys() - b_now.keys()]
        positive += [f"Penalty resolved: {item}" for item in resolved_p] + [f"Blocker resolved: {item}" for item in resolved_b]
        negative += [f"New penalty: {item}" for item in new_p] + [f"New blocker: {item}" for item in new_b]
        if current.contradiction_count < previous.contradiction_count: positive.append("Contradiction count decreased.")
        if current.contradiction_count > previous.contradiction_count: negative.append("Contradiction count increased.")
        if current.ranking_ready and not previous.ranking_ready: positive.append("Ranking readiness was gained.")
        if previous.ranking_ready and not current.ranking_ready: negative.append("Ranking readiness was lost.")
        return positive, negative, new_p, resolved_p, new_b, resolved_b, strongest, weakest

    @staticmethod
    def _canonical(value: str) -> str:
        code = str(value).split(":", 1)[0]
        return re.sub(r"[^A-Z0-9]+", "_", code.upper()).strip("_")

    @classmethod
    def _canonical_map(cls, values: tuple[str, ...]) -> dict[str, str]:
        return {cls._canonical(value): value for value in values}

    @staticmethod
    def _alignment(context: DecisionContext, current: DecisionConfidence, eligible: bool) -> tuple[str, str, list[str]]:
        recommendation = context.recommendation
        side = str(recommendation.get("side", "")).upper() if isinstance(recommendation, Mapping) else ""
        evidence = context.institutional_evidence
        bias = str(getattr(evidence, "bias", "")).upper() if evidence is not None else ""
        flags: list[str] = []
        if not side:
            flags.append("RECOMMENDATION_UNAVAILABLE"); return "UNAVAILABLE", "The live recommendation is unavailable for shadow comparison.", flags
        if not bias or bias == "UNAVAILABLE":
            flags.append("INSTITUTIONAL_EVIDENCE_UNAVAILABLE"); return "UNAVAILABLE", "Institutional evidence is unavailable for shadow comparison.", flags
        if side == "WAIT":
            return "RECOMMENDATION_WAIT", f"Decision Confidence is {current.grade.replace('_', ' ').lower()} and institutional evidence is {bias.lower()}, while the live recommendation remains WAIT.", flags
        expected = "BULLISH" if "CE" in side else "BEARISH" if "PE" in side else ""
        if bias == expected:
            return "ALIGNED", f"The live recommendation and {bias.lower()} institutional evidence are aligned in shadow validation.", flags
        if bias in {"NEUTRAL", "MIXED"}:
            return "DIRECTIONALLY_ALIGNED", "Institutional evidence is neutral or mixed relative to the live recommendation.", flags
        return "CONFLICTED", "The live recommendation conflicts with institutional evidence in shadow validation.", flags

    @staticmethod
    def _explanations(trend: str, stability: str, agreement: float, persistence: float, eligibility: str, blockers: list[str]) -> tuple[str, ...]:
        values = [f"Trend is {trend.lower().replace('_', ' ')} across normalized analysis points.", f"Stability is {stability.lower().replace('_', ' ')} at the configured dispersion thresholds.", f"Pillar agreement is {agreement:.1f}/100.", f"Ranking-readiness persistence is {persistence:.1f}% using documented recent weighting.", f"Ranking eligibility is {eligibility.lower().replace('_', ' ')}."]
        if blockers: values.append("New blockers: " + ", ".join(blockers) + ".")
        return tuple(values)

    @staticmethod
    def _narrative(trend: str, stability: str, agreement: float, strongest: str | None, weakest: str | None, blockers: list[str], eligibility: str, enough: bool) -> str:
        text = f"Decision confidence trend is {trend.lower().replace('_', ' ')} with {stability.lower().replace('_', ' ')} stability and pillar agreement of {agreement:.1f}/100."
        if strongest: text += f" {strongest.replace('_', ' ').title()} is the strongest improving pillar."
        if weakest: text += f" {weakest.replace('_', ' ').title()} is the weakest deteriorating pillar."
        text += " No new blocker is present." if not blockers else " New blockers are present: " + ", ".join(blockers) + "."
        if not enough: text += " History is insufficient for a persistent conclusion."
        text += f" The setup is {eligibility.lower().replace('_', ' ')} for future option-candidate ranking; this is informational only."
        return text

    @staticmethod
    def _unavailable() -> DecisionConfidenceValidation:
        return DecisionConfidenceValidation(0, None, None, "UNAVAILABLE", "UNAVAILABLE", 0, 0, False, 0, False, "UNAVAILABLE", 0, 0, 0, 0, None, None, (), (), (), (), (), (), "UNAVAILABLE", "Decision confidence is unavailable for shadow comparison.", 0, ("DECISION_CONFIDENCE_UNAVAILABLE", "RANKING_NOT_ELIGIBLE", "VALIDATION_CONFIDENCE_LOW"), ("Decision confidence validation is unavailable.",), "Decision confidence validation is unavailable; ranking eligibility cannot be established.")
