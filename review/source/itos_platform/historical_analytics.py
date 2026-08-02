"""Immutable, read-only Historical Analytics over the Historical Market Lake.

This module has no dependency on providers, replay runners, ingestion, enrichment,
or the Decision Pipeline.  It queries defensive copies from the lake and computes
factual aggregates; missing data remains missing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from enum import Enum
import json
from statistics import mean, median
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd

from .market_lake import (
    DatasetManifest, HistoricalIntelligenceRecord, HistoricalOutcomeRecord,
    IntelligenceQuery, MarketLakeSettings, PeriodPreset, resolve_period,
)


class WorkspaceMode(str, Enum):
    LIVE = "LIVE"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    HISTORICAL_ANALYTICS = "HISTORICAL_ANALYTICS"
    SAMPLE_DATA = "SAMPLE_DATA"


@dataclass(frozen=True)
class HistoricalAnalyticsRequest:
    instrument_key: str
    underlying: str
    start_date: date
    end_date: date
    interval_minutes: int
    engine_version: str | None = None
    recommendation: str | None = None
    minimum_confidence: float | None = None
    maximum_confidence: float | None = None
    minimum_compression: float | None = None
    maximum_compression: float | None = None
    positioning_state: str | None = None
    manipulation_state: str | None = None
    institutional_bias: str | None = None
    replay_completeness: str | None = None

    def validate(self, settings: MarketLakeSettings = MarketLakeSettings()) -> None:
        if not self.instrument_key.strip() or not self.underlying.strip():
            raise ValueError("underlying and instrument_key are required")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if self.interval_minutes not in settings.supported_intervals:
            raise ValueError("unsupported interval")
        for low, high, label in ((self.minimum_confidence, self.maximum_confidence, "confidence"),
                                 (self.minimum_compression, self.maximum_compression, "compression")):
            if low is not None and high is not None and low > high:
                raise ValueError(f"minimum {label} cannot exceed maximum {label}")


@dataclass(frozen=True)
class HistoricalMetricSummary:
    name: str
    count: int
    percentage: float | None = None
    average: float | None = None
    median: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalAnalyticsResult:
    request: HistoricalAnalyticsRequest
    record_count: int
    trading_day_count: int
    expected_session_count: int
    raw_session_count: int
    intelligence_session_count: int
    outcome_session_count: int
    option_session_count: int
    data_completeness: float
    intelligence_completeness: float
    outcome_completeness: float
    option_completeness: float
    schema_versions: tuple[str, ...]
    engine_versions: tuple[str, ...]
    available_dates: tuple[date, ...]
    missing_dates: tuple[date, ...]
    recommendation_counts: tuple[tuple[str, int], ...]
    market_bias_counts: tuple[tuple[str, int], ...]
    positioning_counts: tuple[tuple[str, int], ...]
    compression_counts: tuple[tuple[str, int], ...]
    manipulation_counts: tuple[tuple[str, int], ...]
    average_confidence: float | None
    median_confidence: float | None
    maximum_confidence: float | None
    minimum_confidence: float | None
    confidence_above_90: int
    confidence_above_80: int
    confidence_above_70: int
    confidence_below_60: int
    ranking_eligible_count: int
    ranking_conditional_count: int
    ranking_rejected_count: int
    average_compression: float | None
    median_compression: float | None
    highest_compression: float | None
    compression_release_count: int
    market_structure: Mapping[str, Any]
    price_volume: Mapping[str, Any]
    positioning: Mapping[str, Any]
    compression: Mapping[str, Any]
    manipulation: Mapping[str, Any]
    institutional_evidence: Mapping[str, Any]
    validation: Mapping[str, Any]
    ranking: Mapping[str, Any]
    top_ce_occurrences: tuple[tuple[str, int], ...]
    top_pe_occurrences: tuple[tuple[str, int], ...]
    top_overall_occurrences: tuple[tuple[str, int], ...]
    average_5m_change: float | None
    average_15m_change: float | None
    average_30m_change: float | None
    average_eod_change: float | None
    average_mfe: float | None
    average_mae: float | None
    future_data_coverage: float
    records: tuple[HistoricalIntelligenceRecord, ...]
    outcome_records: tuple[HistoricalOutcomeRecord, ...]
    detail_rows: tuple[Mapping[str, Any], ...]
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]


class HistoricalAnalyticsLake(Protocol):
    settings: MarketLakeSettings
    def query_intelligence(self, query: IntelligenceQuery) -> tuple[HistoricalIntelligenceRecord, ...]: ...
    def query_outcomes(self, instrument_key: str, start_date: date, end_date: date,
                       engine_version: str) -> tuple[HistoricalOutcomeRecord, ...]: ...
    def get_manifest(self, provider: str, instrument_key: str, interval: int) -> DatasetManifest | None: ...


def resolve_analytics_period(preset: PeriodPreset, end_date: date,
                             custom_start: date | None = None) -> tuple[date, date]:
    return resolve_period(preset, end_date, custom_start=custom_start)


def _value(values: Mapping[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        current: Any = values
        for name in path.split("."):
            current = current.get(name) if isinstance(current, Mapping) else getattr(current, name, None)
            if current is None: break
        if current is not None: return current
    return default


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return None if pd.isna(result) else result
    except (TypeError, ValueError): return None


def _numbers(values: Sequence[Any]) -> list[float]:
    return [number for value in values if (number := _number(value)) is not None]


def _average(values: Sequence[Any]) -> float | None:
    items = _numbers(values); return round(mean(items), 4) if items else None


def _median(values: Sequence[Any]) -> float | None:
    items = _numbers(values); return round(median(items), 4) if items else None


def _counts(values: Sequence[Any]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for value in values:
        label = str(value).strip() if value not in (None, "") else "UNAVAILABLE"
        counts[label] = counts.get(label, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _common(values: Sequence[Any]) -> str | None:
    counts = _counts(values); return counts[0][0] if counts else None


def _flag(record: HistoricalIntelligenceRecord, *paths: str) -> bool:
    value = _value(record.values, *paths, default=False)
    return value is True or str(value).upper() in {"TRUE", "YES", "DETECTED", "CONFIRMED", "RELEASING", "EXPANDING"}


def _pct(count: int, total: int) -> float:
    return round(100.0 * count / total, 2) if total else 0.0


def _sessions(values: Sequence[date], request: HistoricalAnalyticsRequest) -> tuple[date, ...]:
    return tuple(sorted({day for day in values if request.start_date <= day <= request.end_date}))


class HistoricalAnalyticsService:
    """Market-Lake-only deterministic query and aggregation service."""
    def __init__(self, lake: HistoricalAnalyticsLake, *, provider: str = "upstox") -> None:
        self._lake, self.provider = lake, provider

    def analyze(self, request: HistoricalAnalyticsRequest) -> HistoricalAnalyticsResult:
        request.validate(self._lake.settings)
        manifest = self._lake.get_manifest(self.provider, request.instrument_key, request.interval_minutes)
        engine = request.engine_version or (manifest.engine_version if manifest else self._lake.settings.engine_version)
        stored = self._lake.query_intelligence(IntelligenceQuery(
            request.instrument_key, request.start_date, request.end_date, request.interval_minutes,
            engine_version=engine,
        ))
        records = tuple(record for record in stored if self._matches(record, request))
        stored_outcomes = self._lake.query_outcomes(request.instrument_key, request.start_date, request.end_date, engine)
        record_ids = {record.record_id for record in records}
        outcomes = tuple(outcome for outcome in stored_outcomes if outcome.intelligence_record_id in record_ids)
        return self._aggregate(request, records, outcomes, manifest)

    @staticmethod
    def _matches(record: HistoricalIntelligenceRecord, request: HistoricalAnalyticsRequest) -> bool:
        confidence = _number(record.decision_confidence)
        compression = _number(_value(record.values, "compression_intelligence.score", "compression.score"))
        tests = (
            request.engine_version is None or record.engine_version == request.engine_version,
            request.recommendation is None or record.recommendation == request.recommendation,
            request.minimum_confidence is None or confidence is not None and confidence >= request.minimum_confidence,
            request.maximum_confidence is None or confidence is not None and confidence <= request.maximum_confidence,
            request.minimum_compression is None or compression is not None and compression >= request.minimum_compression,
            request.maximum_compression is None or compression is not None and compression <= request.maximum_compression,
            request.positioning_state is None or record.positioning_state == request.positioning_state,
            request.manipulation_state is None or record.manipulation_state == request.manipulation_state,
            request.institutional_bias is None or record.market_bias == request.institutional_bias,
            request.replay_completeness is None or record.replay_completeness == request.replay_completeness,
        )
        return all(tests)

    def _aggregate(self, request: HistoricalAnalyticsRequest, records: tuple[HistoricalIntelligenceRecord, ...],
                   outcomes: tuple[HistoricalOutcomeRecord, ...], manifest: DatasetManifest | None) -> HistoricalAnalyticsResult:
        expected = tuple(request.start_date + timedelta(days=index)
                         for index in range((request.end_date-request.start_date).days+1)
                         if (request.start_date+timedelta(days=index)).weekday() < 5)
        raw_dates = _sessions(manifest.available_dates if manifest else (), request)
        intel_dates = _sessions(manifest.intelligence_dates if manifest else (), request)
        outcome_dates = _sessions(manifest.outcome_dates if manifest else (), request)
        option_dates = _sessions(manifest.option_dates if manifest else (), request)
        missing = tuple(day for day in expected if day not in set(raw_dates))
        denominator = len(expected)
        confidence = _numbers([record.decision_confidence for record in records])
        compression_scores = _numbers([_value(record.values, "compression_intelligence.score", "compression.score") for record in records])
        regimes = [_value(record.values, "market_regime.regime", "regime", default=record.market_bias) for record in records]
        cycles = [_value(record.values, "market_cycle.cycle", "cycle") for record in records]
        biases = [_value(record.values, "institutional_evidence.bias", "institutional_bias", default=record.market_bias) for record in records]
        positioning = [record.positioning_state for record in records]
        compression_states = [record.compression_state for record in records]
        manipulation_states = [record.manipulation_state for record in records]
        recommendation = [record.recommendation for record in records]
        bullish = sum("BULL" in str(value).upper() for value in regimes)
        bearish = sum("BEAR" in str(value).upper() for value in regimes)
        neutral = len(records)-bullish-bearish
        evidence_bull = sum("BULL" in str(value).upper() for value in biases)
        evidence_bear = sum("BEAR" in str(value).upper() for value in biases)
        evidence_neutral = len(records)-evidence_bull-evidence_bear
        top_ce = [_value(r.values, "trade_opportunity_ranking.top_ce.strike", "top_ce.strike") for r in records]
        top_pe = [_value(r.values, "trade_opportunity_ranking.top_pe.strike", "top_pe.strike") for r in records]
        top_overall = [_value(r.values, "trade_opportunity_ranking.best_overall.strike", "best_overall.strike") for r in records]
        blockers = [item for record in records for item in record.blockers]
        confirmations = [item for record in records for item in record.missing_confirmations]
        conditional = sum(str(_value(r.values, "trade_opportunity_ranking.eligibility", "ranking_eligibility")).upper() == "CONDITIONAL" for r in records)
        horizon = lambda minutes: _average([dict(outcome.horizon_point_changes).get(minutes) for outcome in outcomes])
        eod = [None if outcome.end_of_session_price is None else outcome.end_of_session_price-outcome.reference_price for outcome in outcomes]
        outcome_by_id = {outcome.intelligence_record_id: outcome for outcome in outcomes}
        fallback_engine_version = (
            manifest.engine_version if manifest is not None
            else self._lake.settings.engine_version
        )
        quality = set(flag for record in records for flag in record.quality_flags)
        explanations = []
        if missing: quality.add("RAW_DATA_MISSING"); explanations.append("Historical data is incomplete for this period.")
        if not records: quality.add("NO_STORED_INTELLIGENCE"); explanations.append("No stored intelligence matches the selected filters.")
        result = HistoricalAnalyticsResult(
            request, len(records), len({r.trading_date for r in records}), denominator, len(raw_dates), len(intel_dates),
            len(outcome_dates), len(option_dates), _pct(len(raw_dates), denominator), _pct(len(intel_dates), denominator),
            _pct(len(outcome_dates), denominator), _pct(len(option_dates), denominator),
            tuple(sorted({r.schema_version for r in records} or {self._lake.settings.intelligence_schema_version})),
            tuple(sorted({r.engine_version for r in records} or {fallback_engine_version})), raw_dates, missing,
            _counts(recommendation), _counts([r.market_bias for r in records]), _counts(positioning),
            _counts(compression_states), _counts(manipulation_states), _average(confidence), _median(confidence),
            max(confidence, default=None), min(confidence, default=None), sum(v >= 90 for v in confidence),
            sum(v >= 80 for v in confidence), sum(v >= 70 for v in confidence), sum(v < 60 for v in confidence),
            sum(r.ranking_eligibility for r in records), conditional, sum(not r.ranking_eligibility for r in records),
            _average(compression_scores), _median(compression_scores), max(compression_scores, default=None),
            sum(_flag(r, "compression_intelligence.releasing", "compression.release") for r in records),
            {"bullish_count": bullish, "bullish_percentage": _pct(bullish, len(records)), "bearish_count": bearish,
             "bearish_percentage": _pct(bearish, len(records)), "neutral_count": neutral,
             "neutral_percentage": _pct(neutral, len(records)), "most_common_market_cycle": _common(cycles),
             "most_common_regime": _common(regimes), "transition_count": sum(a != b for a, b in zip(regimes, regimes[1:]))},
            {"average_volume_strength": _average([_value(r.values, "volume_structure.volume_strength", "volume_strength") for r in records]),
             "price_up_volume_up_count": sum(_flag(r, "volume_structure.price_up_volume_up") for r in records),
             "price_down_volume_up_count": sum(_flag(r, "volume_structure.price_down_volume_up") for r in records),
             "confirmed_expansions": sum(_flag(r, "volume_structure.confirmed_expansion") for r in records),
             "weak_or_unconfirmed_moves": sum(_flag(r, "volume_structure.weak_move", "volume_structure.unconfirmed_move") for r in records),
             "accumulation_count": sum("ACCUMULATION" in str(_value(r.values, "volume_structure.behaviour", default="")).upper() for r in records),
             "distribution_count": sum("DISTRIBUTION" in str(_value(r.values, "volume_structure.behaviour", default="")).upper() for r in records)},
            {"long_build_up_count": sum(str(v).upper() == "LONG BUILD-UP" for v in positioning),
             "short_build_up_count": sum(str(v).upper() == "SHORT BUILD-UP" for v in positioning),
             "long_unwinding_count": sum(str(v).upper() == "LONG UNWINDING" for v in positioning),
             "short_covering_count": sum(str(v).upper() == "SHORT COVERING" for v in positioning),
             "call_writing_count": sum(str(v).upper() == "CALL WRITING" for v in positioning),
             "put_writing_count": sum(str(v).upper() == "PUT WRITING" for v in positioning),
             "most_common_positioning_state": _common(positioning)},
            {"average": _average(compression_scores), "median": _median(compression_scores),
             "highest": max(compression_scores, default=None),
             "high_or_extreme_count": sum(str(v).upper() in {"HIGH", "EXTREME"} for v in compression_states),
             "releasing_count": sum(_flag(r, "compression_intelligence.releasing", "compression.release") for r in records),
             "expanding_count": sum(_flag(r, "compression_intelligence.expanding", "compression.expanding") for r in records)},
            {name: sum(_flag(r, f"manipulation_intelligence.{name}", f"manipulation.{name}") for r in records)
             for name in ("false_breakout", "false_breakdown", "liquidity_sweep", "bull_trap", "bear_trap")},
            {"bullish_count": evidence_bull, "bullish_percentage": _pct(evidence_bull, len(records)),
             "bearish_count": evidence_bear, "bearish_percentage": _pct(evidence_bear, len(records)),
             "neutral_or_conflicted_count": evidence_neutral, "neutral_or_conflicted_percentage": _pct(evidence_neutral, len(records)),
             "average_evidence_quality": _average([_value(r.values, "institutional_evidence.quality") for r in records])},
            {"ranking_eligible_count": sum(r.ranking_eligibility for r in records), "conditional_count": conditional,
             "not_eligible_count": sum(not r.ranking_eligibility for r in records), "primary_blocker_counts": _counts(blockers),
             "missing_confirmation_counts": _counts(confirmations)},
            {"buy_ce_count": recommendation.count("BUY CE"), "buy_pe_count": recommendation.count("BUY PE"),
             "wait_count": recommendation.count("WAIT"), "best_ce_frequency": _counts(top_ce), "best_pe_frequency": _counts(top_pe),
             "best_overall_frequency": _counts(top_overall), "ranking_eligible_count": sum(r.ranking_eligibility for r in records),
             "ranking_unavailable_count": sum(_value(r.values, "trade_opportunity_ranking", default=None) is None for r in records)},
            _counts(top_ce)[:5], _counts(top_pe)[:5], _counts(top_overall)[:5],
            horizon(5), horizon(15), horizon(30), _average(eod),
            _average([o.maximum_favourable_excursion for o in outcomes]),
            _average([o.maximum_adverse_excursion for o in outcomes]),
            _pct(sum(o.future_data_available for o in outcomes), len(records)), records, outcomes,
            tuple(self._detail(record, outcome_by_id.get(record.record_id)) for record in records),
            tuple(sorted(quality)), tuple(explanations),
        )
        return result

    @staticmethod
    def _detail(record: HistoricalIntelligenceRecord, outcome: HistoricalOutcomeRecord | None) -> Mapping[str, Any]:
        changes = dict(outcome.horizon_point_changes) if outcome else {}
        return {"Date": record.trading_date.isoformat(), "Time": record.analysis_timestamp.isoformat(),
            "Recommendation": record.recommendation, "Recommendation Confidence": record.recommendation_confidence,
            "Institutional Bias": record.market_bias, "Positioning": record.positioning_state,
            "Compression State": record.compression_state,
            "Compression Score": _number(_value(record.values, "compression_intelligence.score", "compression.score")),
            "Manipulation State": record.manipulation_state, "Decision Confidence": record.decision_confidence,
            "Ranking Eligibility": record.ranking_eligibility,
            "Best CE": _value(record.values, "trade_opportunity_ranking.top_ce.strike", "top_ce.strike"),
            "Best PE": _value(record.values, "trade_opportunity_ranking.top_pe.strike", "top_pe.strike"),
            "Replay Completeness": record.replay_completeness, "5m Outcome": changes.get(5),
            "15m Outcome": changes.get(15), "30m Outcome": changes.get(30),
            "EOD Outcome": None if not outcome or outcome.end_of_session_price is None else outcome.end_of_session_price-outcome.reference_price,
            "Quality Flags": tuple(sorted(set(record.quality_flags) | set(outcome.quality_flags if outcome else ())))}

    @staticmethod
    def export_csv(result: HistoricalAnalyticsResult) -> bytes:
        return pd.DataFrame(result.detail_rows).to_csv(index=False).encode("utf-8")

    @staticmethod
    def export_json(result: HistoricalAnalyticsResult) -> bytes:
        def encode(value: Any) -> Any:
            if isinstance(value, (date,)): return value.isoformat()
            if isinstance(value, Enum): return value.value
            raise TypeError(f"unsupported export value: {type(value).__name__}")
        payload = {"request": asdict(result.request), "summary": {
            "record_count": result.record_count, "trading_day_count": result.trading_day_count,
            "data_completeness": result.data_completeness, "intelligence_completeness": result.intelligence_completeness,
            "outcome_completeness": result.outcome_completeness, "option_completeness": result.option_completeness,
            "quality_flags": result.quality_flags}, "records": result.detail_rows}
        return json.dumps(payload, default=encode, sort_keys=True).encode("utf-8")
