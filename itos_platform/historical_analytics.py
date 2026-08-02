"""Read-only aggregation for the Historical Analytics workspace.

The service intentionally depends only on the Market Lake query contract.  It never
owns a provider, downloader, replay runner, or decision pipeline, which makes the
read-only performance guarantee enforceable rather than merely a UI convention.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from io import BytesIO
from statistics import mean, median
from typing import Any, Mapping, Sequence

import pandas as pd

from .market_lake import (
    DatasetManifest, HistoricalIntelligenceRecord, HistoricalOutcomeRecord,
    IntelligenceQuery, LocalHistoricalMarketLake, PeriodPreset, resolve_period,
)


PERIOD_LABELS: Mapping[str, PeriodPreset] = {
    "Week": PeriodPreset.WEEK, "Month": PeriodPreset.MONTH,
    "3 Months": PeriodPreset.THREE_MONTHS, "6 Months": PeriodPreset.SIX_MONTHS,
    "1 Year": PeriodPreset.ONE_YEAR, "Custom Range": PeriodPreset.CUSTOM,
}


@dataclass(frozen=True)
class AnalyticsFilters:
    recommendation: str | None = None
    minimum_confidence: float | None = None
    maximum_confidence: float | None = None
    minimum_compression: float | None = None
    maximum_compression: float | None = None
    manipulation: str | None = None
    positioning: str | None = None
    institutional_bias: str | None = None
    replay_completeness: str | None = None
    search: str = ""


@dataclass(frozen=True)
class AnalyticsHeader:
    underlying: str
    selected_period: str
    trading_days: int
    analysis_points: int
    engine_version: str
    data_completeness: float
    option_completeness: float
    market_lake_status: str
    available_dates: tuple[date, ...] = ()
    missing_dates: tuple[date, ...] = ()


@dataclass(frozen=True)
class HistoricalAnalyticsResult:
    header: AnalyticsHeader
    cards: Mapping[str, Mapping[str, Any]]
    records: tuple[HistoricalIntelligenceRecord, ...]
    outcomes: tuple[HistoricalOutcomeRecord, ...]
    detail_rows: tuple[Mapping[str, Any], ...]


def _nested(values: Mapping[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        current: Any = values
        for part in path.split("."):
            if isinstance(current, Mapping): current = current.get(part)
            else: current = getattr(current, part, None)
            if current is None: break
        if current is not None: return current
    return default


def _number(value: Any) -> float | None:
    try: return float(value)
    except (TypeError, ValueError): return None


def _average(values: Sequence[Any]) -> float | None:
    numbers = [item for value in values if (item := _number(value)) is not None]
    return round(mean(numbers), 2) if numbers else None


def _percent(records: Sequence[Any], predicate: Any) -> float:
    return round(100 * sum(bool(predicate(item)) for item in records) / len(records), 2) if records else 0.0


def _distribution(values: Sequence[str | None]) -> Mapping[str, int]:
    result: dict[str, int] = {}
    for value in values:
        label = value or "Unknown"; result[label] = result.get(label, 0) + 1
    return dict(sorted(result.items(), key=lambda item: (-item[1], item[0])))


def _common(values: Sequence[str | None]) -> str:
    distribution = _distribution(values)
    return next(iter(distribution), "Unavailable")


def _truth(record: HistoricalIntelligenceRecord, *paths: str) -> bool:
    value = _nested(record.values, *paths, default=False)
    return value is True or str(value).upper() in {"TRUE", "YES", "CONFIRMED", "DETECTED"}


class HistoricalAnalyticsService:
    """Queries stored intelligence/outcomes and produces existing-card values."""

    def __init__(self, lake: LocalHistoricalMarketLake, *, provider: str = "upstox") -> None:
        self.lake, self.provider = lake, provider

    def analyze(self, *, underlying: str, instrument_key: str, period: str | PeriodPreset,
                end_date: date, start_date: date | None = None, interval_minutes: int | None = None,
                filters: AnalyticsFilters = AnalyticsFilters()) -> HistoricalAnalyticsResult:
        preset = PERIOD_LABELS.get(str(period), period)
        if not isinstance(preset, PeriodPreset): preset = PeriodPreset(str(preset))
        start, end = resolve_period(preset, end_date, custom_start=start_date)
        manifest = self.lake.get_manifest(self.provider, instrument_key, interval_minutes or 1)
        engine = manifest.engine_version if manifest else self.lake.settings.engine_version
        query = IntelligenceQuery(instrument_key, start, end, interval_minutes,
            recommendation=filters.recommendation, positioning_state=filters.positioning,
            manipulation_state=filters.manipulation, market_bias=filters.institutional_bias,
            minimum_confidence=filters.minimum_confidence, maximum_confidence=filters.maximum_confidence,
            replay_completeness=filters.replay_completeness, engine_version=engine)
        records = tuple(r for r in self.lake.query_intelligence(query) if self._extra_match(r, filters))
        outcomes = self.lake.query_outcomes(instrument_key, start, end, engine)
        outcome_ids = {item.intelligence_record_id for item in outcomes}
        outcomes = tuple(item for item in outcomes if item.intelligence_record_id in {r.record_id for r in records})
        expected = tuple(start + timedelta(days=n) for n in range((end-start).days + 1)
                         if (start + timedelta(days=n)).weekday() < 5)
        available = tuple(d for d in (manifest.intelligence_dates if manifest else ()) if start <= d <= end)
        missing = tuple(d for d in expected if d not in set(available))
        option_dates = set(manifest.option_dates if manifest else ())
        data_complete = round(100 * len(available) / len(expected), 2) if expected else 0.0
        option_complete = round(100 * len(option_dates.intersection(expected)) / len(expected), 2) if expected else 0.0
        header = AnalyticsHeader(underlying, str(period), len({r.trading_date for r in records}), len(records),
            engine, data_complete, option_complete, "READY" if not missing else "INCOMPLETE", available, missing)
        rows = tuple(self._detail(r, next((o for o in outcomes if o.intelligence_record_id == r.record_id), None)) for r in records)
        return HistoricalAnalyticsResult(header, self._cards(records, outcomes), records, outcomes, rows)

    @staticmethod
    def _extra_match(record: HistoricalIntelligenceRecord, filters: AnalyticsFilters) -> bool:
        compression = _number(_nested(record.values, "compression.score", "compression_intelligence.score"))
        if filters.minimum_compression is not None and (compression is None or compression < filters.minimum_compression): return False
        if filters.maximum_compression is not None and (compression is None or compression > filters.maximum_compression): return False
        needle = filters.search.strip().lower()
        if needle and needle not in " ".join((str(record.trading_date), record.analysis_timestamp.strftime("%H:%M"),
                                               record.recommendation, str(record.decision_confidence))).lower(): return False
        return True

    @staticmethod
    def _cards(records: Sequence[HistoricalIntelligenceRecord], outcomes: Sequence[HistoricalOutcomeRecord]) -> Mapping[str, Mapping[str, Any]]:
        biases = [str(_nested(r.values, "institutional_evidence.bias", "institutional_bias", default=r.market_bias) or "Neutral") for r in records]
        regimes = [str(_nested(r.values, "market_regime.regime", "regime", default=r.market_bias)) for r in records]
        cycles = [str(_nested(r.values, "market_cycle.cycle", "cycle")) for r in records]
        confidence = [v for r in records if (v := _number(r.decision_confidence)) is not None]
        compression = [_nested(r.values, "compression.score", "compression_intelligence.score") for r in records]
        recommendations = [r.recommendation.upper() for r in records]
        positions = [r.positioning_state for r in records]
        strikes = lambda side: [str(_nested(r.values, f"trade_opportunity_ranking.top_{side.lower()}.strike",
            f"top_{side.lower()}.strike", default="Unavailable")) for r in records if r.recommendation.upper() == f"BUY {side}"]
        def top_five(side: str) -> tuple[Mapping[str, Any], ...]:
            values = strikes(side); dist = _distribution(values)
            return tuple({"strike": strike, "occurrences": count,
                          "average_confidence": _average([r.decision_confidence for r in records
                              if r.recommendation.upper() == f"BUY {side}" and strike == str(_nested(r.values, f"trade_opportunity_ranking.top_{side.lower()}.strike", f"top_{side.lower()}.strike", default="Unavailable"))])}
                         for strike, count in list(dist.items())[:5])
        horizon = lambda minutes: _average([dict(o.horizon_point_changes).get(minutes) for o in outcomes])
        return {
            "market_structure": {"bullish_percent": _percent(regimes, lambda v: "BULL" in v.upper()), "bearish_percent": _percent(regimes, lambda v: "BEAR" in v.upper()), "neutral_percent": _percent(regimes, lambda v: "BULL" not in v.upper() and "BEAR" not in v.upper()), "transitions": sum(a != b for a, b in zip(regimes, regimes[1:])), "most_common_regime": _common(regimes), "most_common_cycle": _common(cycles)},
            "price_volume": {"average_volume_strength": _average([_nested(r.values, "volume_structure.strength", "volume_strength") for r in records]), "confirmed_breakouts": sum(_truth(r, "volume_structure.confirmed_breakout", "confirmed_breakout") for r in records), "failed_breakouts": sum(_truth(r, "failed_breakout", "manipulation.false_breakout") for r in records), "average_trend_strength": _average([_nested(r.values, "trend_strength", "price.trend_strength") for r in records]), "vwap_acceptance_percent": _percent(records, lambda r: _truth(r, "vwap_acceptance", "price.vwap_acceptance"))},
            "positioning": {**_distribution(positions), "most_common_positioning": _common(positions)},
            "compression": {"average_compression": _average(compression), "highest_compression": max((_number(v) for v in compression if _number(v) is not None), default=None), "compression_releases": sum(_truth(r, "compression.release", "compression_release") for r in records), "false_releases": sum(_truth(r, "compression.false_release", "false_release") for r in records), "distribution": _distribution([r.compression_state for r in records])},
            "manipulation": {name: sum(_truth(r, f"manipulation.{name}", name) for r in records) for name in ("false_breakouts", "false_breakdowns", "liquidity_sweeps", "bull_traps", "bear_traps")},
            "institutional_evidence": {"bullish_percent": _percent(biases, lambda v: "BULL" in v.upper()), "bearish_percent": _percent(biases, lambda v: "BEAR" in v.upper()), "neutral_percent": _percent(biases, lambda v: "BULL" not in v.upper() and "BEAR" not in v.upper()), "institutional_participation": _average([_nested(r.values, "institutional_evidence.participation", "institutional_participation") for r in records])},
            "decision_confidence": {"average": _average(confidence), "median": round(median(confidence), 2) if confidence else None, "maximum": max(confidence, default=None), "minimum": min(confidence, default=None), **{f"above_{n}": sum(v >= n for v in confidence) for n in (90, 80, 70)}, "below_60": sum(v < 60 for v in confidence)},
            "validation": {"eligible_trades": sum(r.ranking_eligibility for r in records), "rejected_trades": sum(not r.ranking_eligibility for r in records), "missing_confirmations": sum(len(r.missing_confirmations) for r in records), "safety_blocks": sum(len(r.blockers) for r in records)},
            "trade_opportunity_ranking": {"buy_ce": recommendations.count("BUY CE"), "buy_pe": recommendations.count("BUY PE"), "wait": recommendations.count("WAIT"), "top_ranked_ce": _common(strikes("CE")), "top_ranked_pe": _common(strikes("PE"))},
            "top_5_ce": {"recommendations": top_five("CE")}, "top_5_pe": {"recommendations": top_five("PE")},
            "historical_outcomes": {"average": _average([v for o in outcomes for _, v in o.horizon_point_changes]), "5_minutes": horizon(5), "15_minutes": horizon(15), "30_minutes": horizon(30), "end_of_day": _average([None if o.end_of_session_price is None else o.end_of_session_price-o.reference_price for o in outcomes]), "mfe": _average([o.maximum_favourable_excursion for o in outcomes]), "mae": _average([o.maximum_adverse_excursion for o in outcomes])},
        }

    @staticmethod
    def _detail(record: HistoricalIntelligenceRecord, outcome: HistoricalOutcomeRecord | None) -> Mapping[str, Any]:
        return {"Date": record.trading_date.isoformat(), "Time": record.analysis_timestamp.strftime("%H:%M:%S"),
            "Recommendation": record.recommendation, "Confidence": record.decision_confidence,
            "Positioning": record.positioning_state, "Compression": record.compression_state,
            "Manipulation": record.manipulation_state, "Institutional Bias": record.market_bias,
            "Top CE": _nested(record.values, "trade_opportunity_ranking.top_ce.strike", "top_ce.strike"),
            "Top PE": _nested(record.values, "trade_opportunity_ranking.top_pe.strike", "top_pe.strike"),
            "Replay Completeness": record.replay_completeness,
            "Outcome": None if outcome is None else dict(outcome.horizon_point_changes)}

    @staticmethod
    def export_csv(result: HistoricalAnalyticsResult) -> bytes:
        return pd.DataFrame(result.detail_rows).to_csv(index=False).encode("utf-8")

    @staticmethod
    def export_parquet(result: HistoricalAnalyticsResult) -> bytes:
        output = BytesIO(); pd.DataFrame(result.detail_rows).to_parquet(output, index=False); return output.getvalue()
