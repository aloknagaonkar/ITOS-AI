"""Contracts and orchestration for authenticated Upstox Market Lake synchronization."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Sequence
import time

import pandas as pd

from .market_lake import (
    DatasetManifest, HistoricalEnrichmentService, HistoricalIngestionService,
    HistoricalOutcomeService, HistoricalRangeRequest, IntelligenceQuery,
    LocalHistoricalMarketLake, MarketLakeSettings, PeriodPreset, new_manifest,
    resolve_period,
)


@dataclass(frozen=True)
class HistoricalInstrument:
    display_name: str
    instrument_key: str
    exchange: str = "NSE"
    supported_intervals: tuple[int, ...] = (1, 3, 5, 10, 15, 30, 60)
    data_source: str = "Upstox Historical Candle V3"


DEFAULT_HISTORICAL_INSTRUMENTS: Mapping[str, HistoricalInstrument] = {
    "NIFTY": HistoricalInstrument("NIFTY", "NSE_INDEX|Nifty 50"),
    "BANKNIFTY": HistoricalInstrument("BANKNIFTY", "NSE_INDEX|Nifty Bank"),
}


def resolve_historical_instrument(
    underlying: str, configured: Mapping[str, HistoricalInstrument] = DEFAULT_HISTORICAL_INSTRUMENTS,
) -> HistoricalInstrument:
    try:
        return configured[underlying.strip().upper()]
    except KeyError as error:
        raise ValueError(f"unsupported historical underlying: {underlying}") from error


@dataclass(frozen=True)
class HistoricalSyncSettings:
    upstox_historical_sync_enabled: bool = True
    historical_sync_provider: str = "upstox"
    historical_sync_chunk_days_by_interval: tuple[tuple[int, int], ...] = (
        (1, 30), (3, 30), (5, 30), (10, 30), (15, 30), (30, 90), (60, 90),
    )
    historical_sync_retry_attempts: int = 2
    historical_sync_retry_delay_seconds: float = 1.0
    historical_sync_timeout_seconds: float = 20.0
    historical_sync_rate_limit_backoff_seconds: float = 5.0
    historical_sync_default_underlying: str = "NIFTY"
    historical_sync_default_period: PeriodPreset = PeriodPreset.WEEK
    historical_sync_default_interval: int = 1
    historical_sync_default_cadence: int = 5
    historical_sync_maximum_range_days: int = 366
    historical_sync_cancel_check_interval: int = 1
    historical_sync_include_options_default: bool = False
    historical_sync_recommend_pilot_period: PeriodPreset = PeriodPreset.WEEK

    def chunk_days(self, interval: int) -> int:
        chunks = dict(self.historical_sync_chunk_days_by_interval)
        if interval not in chunks:
            raise ValueError(f"unsupported historical interval: {interval}")
        return chunks[interval]


@dataclass(frozen=True)
class DateChunk:
    start_date: date
    end_date: date
    requested_dates: tuple[date, ...]


@dataclass(frozen=True)
class HistoricalSyncPlan:
    instrument_key: str
    underlying: str
    interval_minutes: int
    requested_start: date
    requested_end: date
    expected_dates: tuple[date, ...]
    complete_dates: tuple[date, ...]
    missing_dates: tuple[date, ...]
    incomplete_dates: tuple[date, ...]
    failed_dates: tuple[date, ...]
    dates_to_download: tuple[date, ...]
    dates_to_enrich: tuple[date, ...]
    dates_to_build_outcomes: tuple[date, ...]
    estimated_raw_requests: int
    estimated_analysis_points: int | None
    analysis_cadence_minutes: int
    raw_schema_version: str
    intelligence_schema_version: str
    outcome_schema_version: str
    engine_version: str
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalSyncResult:
    requested_dates: tuple[date, ...]
    completed_dates: tuple[date, ...]
    skipped_dates: tuple[date, ...]
    no_data_dates: tuple[date, ...]
    failed_dates: tuple[date, ...]
    downloaded_row_count: int
    stored_row_count: int
    started_at: datetime
    completed_at: datetime | None
    cancelled: bool
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalSyncProgress:
    phase: str
    current_date: date | None = None
    chunk_number: int = 0
    chunk_count: int = 0
    downloaded_rows: int = 0
    stored_rows: int = 0
    enriched_analysis_points: int = 0
    outcomes_built: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0


class HistoricalProviderError(RuntimeError): pass
class HistoricalAuthenticationError(HistoricalProviderError): pass
class HistoricalRateLimitError(HistoricalProviderError): pass
class HistoricalTimeoutError(HistoricalProviderError): pass
class HistoricalMalformedResponseError(HistoricalProviderError): pass


class UpstoxHistoricalSyncProvider:
    """Thin historical-only adapter around the already authenticated live client."""
    def __init__(self, *, client: Any) -> None:
        if client is None or not callable(getattr(client, "get_historical_candles", None)):
            raise HistoricalAuthenticationError("Historical Upstox authentication failed.")
        self._client = client

    @property
    def authentication_available(self) -> bool:
        return self._client is not None

    def fetch_historical_candles(self, *, instrument_key: str, start_date: date,
                                 end_date: date, interval_minutes: int) -> pd.DataFrame:
        if not instrument_key or start_date > end_date or end_date > date.today():
            raise ValueError("invalid historical instrument or date range")
        try:
            result = self._client.get_historical_candles(
                instrument_key, from_date=start_date.isoformat(), to_date=end_date.isoformat(),
                interval=interval_minutes, unit="minutes",
            )
        except Exception as error:
            status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
            name = type(error).__name__.lower()
            if status in (401, 403) or "auth" in name:
                raise HistoricalAuthenticationError("Historical Upstox authentication failed.") from None
            if status == 429 or "rate" in name:
                raise HistoricalRateLimitError("Upstox historical rate limit reached.") from None
            if "timeout" in name:
                raise HistoricalTimeoutError("Upstox historical request timed out.") from None
            raise HistoricalProviderError("Upstox historical provider unavailable.") from None
        if not isinstance(result, pd.DataFrame):
            raise HistoricalMalformedResponseError("Malformed Upstox historical response.")
        return normalize_historical_candles(result)


def normalize_historical_candles(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize defensively without inventing volume or open interest."""
    if not isinstance(frame, pd.DataFrame):
        raise HistoricalMalformedResponseError("Malformed Upstox historical response.")
    data = frame.copy(deep=True).rename(columns={"oi": "open_interest"})
    required = ("timestamp", "open", "high", "low", "close")
    if not set(required).issubset(data.columns):
        raise HistoricalMalformedResponseError("Malformed Upstox historical response.")
    for optional in ("volume", "open_interest"):
        if optional not in data: data[optional] = pd.NA
    stamps = pd.to_datetime(data["timestamp"], errors="coerce", utc=True)
    data["timestamp"] = stamps.dt.tz_convert("Asia/Kolkata")
    for column in ("open", "high", "low", "close", "volume", "open_interest"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=list(required))
    valid = (data["high"] >= data[["open", "close", "low"]].max(axis=1)) & (data["low"] <= data[["open", "close", "high"]].min(axis=1))
    return (data.loc[valid, [*required, "volume", "open_interest"]]
            .sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True).copy(deep=True))


def expected_weekdays(start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=offset) for offset in range((end-start).days+1)
                 if (start + timedelta(days=offset)).weekday() < 5)


def build_date_chunks(days: Sequence[date], maximum_days: int) -> tuple[DateChunk, ...]:
    """Build bounded calendar ranges without requesting unrelated complete dates."""
    ordered = tuple(sorted(set(days))); chunks: list[DateChunk] = []
    if maximum_days < 1: raise ValueError("chunk days must be positive")
    current: list[date] = []
    for day in ordered:
        if current and ((day-current[0]).days >= maximum_days or (day-current[-1]).days > 1):
            chunks.append(DateChunk(current[0], current[-1], tuple(current))); current = []
        current.append(day)
    if current: chunks.append(DateChunk(current[0], current[-1], tuple(current)))
    return tuple(chunks)


class HistoricalSyncManager:
    def __init__(self, *, provider: UpstoxHistoricalSyncProvider | None,
                 market_lake: LocalHistoricalMarketLake,
                 settings: HistoricalSyncSettings = HistoricalSyncSettings(),
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.provider, self.market_lake, self.settings, self.sleeper = provider, market_lake, settings, sleeper

    @property
    def authentication_available(self) -> bool:
        return bool(self.provider and self.provider.authentication_available)

    def preview_plan(self, request: HistoricalRangeRequest, *, cadence_minutes: int = 5) -> HistoricalSyncPlan:
        request.validate(replace(self.market_lake.settings, maximum_sync_range=self.settings.historical_sync_maximum_range_days))
        expected = expected_weekdays(request.start_date, request.end_date)
        manifest = self.market_lake.get_manifest(self.settings.historical_sync_provider, request.instrument_key, request.interval_minutes)
        manifest = manifest or new_manifest(request, self.settings.historical_sync_provider, self.market_lake.settings)
        complete, incomplete, failed = map(set, (manifest.available_dates, manifest.incomplete_dates, manifest.failed_dates))
        missing = set(expected) - complete
        download = set(expected) if request.rebuild_raw else missing | (incomplete & set(expected))
        raw_ready = complete & set(expected)
        enrich = raw_ready - set(manifest.intelligence_dates)
        outcomes = set(manifest.intelligence_dates) & set(expected) - set(manifest.outcome_dates)
        if request.rebuild_intelligence: enrich = raw_ready
        if request.rebuild_outcomes: outcomes = set(manifest.intelligence_dates) & set(expected)
        chunks = build_date_chunks(tuple(download), self.settings.chunk_days(request.interval_minutes))
        points = len(raw_ready | download) * max(1, 375 // cadence_minutes)
        return HistoricalSyncPlan(request.instrument_key, request.underlying, request.interval_minutes,
            request.start_date, request.end_date, expected, tuple(sorted(complete & set(expected))),
            tuple(sorted(missing)), tuple(sorted(incomplete & set(expected))), tuple(sorted(failed & set(expected))),
            tuple(sorted(download)), tuple(sorted(enrich)), tuple(sorted(outcomes)), len(chunks), points,
            cadence_minutes, manifest.raw_schema_version, manifest.intelligence_schema_version,
            manifest.outcome_schema_version, self.market_lake.settings.engine_version,
            (("OPTIONS_UNAVAILABLE",) if request.include_options else ()),
            ("Historical option-chain snapshots are unavailable for this sync; records are CANDLE_ONLY_REPLAY.",))

    def sync_missing_raw(self, request: HistoricalRangeRequest, *,
                         cancel: Callable[[], bool] = lambda: False,
                         progress: Callable[[HistoricalSyncProgress], None] = lambda _p: None) -> HistoricalSyncResult:
        if not self.authentication_available:
            raise HistoricalAuthenticationError("Historical Upstox authentication failed.")
        plan = self.preview_plan(request); started = datetime.now(timezone.utc)
        chunks = build_date_chunks(plan.dates_to_download, self.settings.chunk_days(request.interval_minutes))
        completed: list[date] = []; failed: list[date] = []; no_data: list[date] = []
        downloaded = stored = 0
        for index, chunk in enumerate(chunks, 1):
            if cancel(): break
            frame = None
            for attempt in range(self.settings.historical_sync_retry_attempts + 1):
                try:
                    frame = self.provider.fetch_historical_candles(instrument_key=request.instrument_key,
                        start_date=chunk.start_date, end_date=chunk.end_date, interval_minutes=request.interval_minutes)
                    break
                except HistoricalAuthenticationError: raise
                except (HistoricalRateLimitError, HistoricalTimeoutError, HistoricalProviderError) as error:
                    if attempt >= self.settings.historical_sync_retry_attempts: break
                    self.sleeper(self.settings.historical_sync_rate_limit_backoff_seconds if isinstance(error, HistoricalRateLimitError) else self.settings.historical_sync_retry_delay_seconds)
            if frame is None:
                failed.extend(chunk.requested_dates); self._checkpoint(request, failed=failed); continue
            downloaded += len(frame)
            trading_dates = frame["timestamp"].dt.date if not frame.empty else pd.Series(dtype=object)
            for day in chunk.requested_dates:
                if cancel(): break
                partition = frame.loc[trading_dates == day].copy(deep=True)
                if partition.empty: no_data.append(day); self._checkpoint(request, no_data=no_data); continue
                try:
                    self.market_lake.store_raw_candles(self.settings.historical_sync_provider, request.instrument_key, request.interval_minutes, day, partition)
                    self.market_lake.store_normalized(request.instrument_key, request.interval_minutes, day, partition)
                    stored += len(partition); completed.append(day); self._checkpoint(request, completed=completed, failed=failed, no_data=no_data)
                except Exception: failed.append(day); self._checkpoint(request, failed=failed)
                progress(HistoricalSyncProgress("raw", day, index, len(chunks), downloaded, stored,
                    completed=len(completed), skipped=len(plan.complete_dates), failed=len(failed)))
        cancelled = cancel()
        return HistoricalSyncResult(plan.dates_to_download, tuple(completed), plan.complete_dates, tuple(no_data),
            tuple(failed), downloaded, stored, started, datetime.now(timezone.utc), cancelled,
            (("CANCELLED",) if cancelled else ()), ("Sync cancelled safely." if cancelled else "Raw sync finished.",))

    def _checkpoint(self, request: HistoricalRangeRequest, *, completed: Sequence[date] = (),
                    failed: Sequence[date] = (), no_data: Sequence[date] = ()) -> None:
        manifest = self.market_lake.get_manifest(self.settings.historical_sync_provider, request.instrument_key, request.interval_minutes)
        manifest = manifest or new_manifest(request, self.settings.historical_sync_provider, self.market_lake.settings)
        available = set(manifest.available_dates) | set(completed)
        failures = (set(manifest.failed_dates) | set(failed)) - available
        absent = (set(manifest.no_data_dates) | set(no_data)) - available
        self.market_lake.put_manifest(replace(manifest, available_dates=tuple(sorted(available)),
            failed_dates=tuple(sorted(failures)), no_data_dates=tuple(sorted(absent)),
            start_date=min(available) if available else manifest.start_date,
            end_date=max(available) if available else manifest.end_date,
            last_ingested_at=datetime.now(timezone.utc)))

    def build_intelligence(self, request: HistoricalRangeRequest, *, runner: Callable[[Any], Any],
                           cadence_minutes: int = 5, cancel: Callable[[], bool] = lambda: False):
        days = [d for d in self.preview_plan(request, cadence_minutes=cadence_minutes).dates_to_enrich if not cancel()]
        result = HistoricalEnrichmentService(self.market_lake, runner, provider=self.settings.historical_sync_provider).enrich(
            request, days, cadence_minutes=cadence_minutes)
        manifest = self.market_lake.get_manifest(self.settings.historical_sync_provider, request.instrument_key, request.interval_minutes)
        if manifest:
            self.market_lake.put_manifest(replace(manifest,
                intelligence_dates=tuple(sorted(set(manifest.intelligence_dates) | set(result.completed_dates))),
                last_enriched_at=datetime.now(timezone.utc)))
        return result

    def build_outcomes(self, request: HistoricalRangeRequest):
        records = self.market_lake.query_intelligence(IntelligenceQuery(request.instrument_key,
            request.start_date, request.end_date, request.interval_minutes,
            engine_version=self.market_lake.settings.engine_version))
        outcomes = HistoricalOutcomeService(self.market_lake, provider=self.settings.historical_sync_provider).build(records)
        manifest = self.market_lake.get_manifest(self.settings.historical_sync_provider, request.instrument_key, request.interval_minutes)
        if manifest:
            built_dates = {record.trading_date for record in outcomes}
            self.market_lake.put_manifest(replace(manifest,
                outcome_dates=tuple(sorted(set(manifest.outcome_dates) | built_dates))))
        return outcomes


def invalidate_historical_analytics_cache(session_state: Mapping[str, Any] | dict[str, Any]) -> None:
    for key in tuple(session_state):
        if str(key).startswith("historical_analytics_") and str(key).endswith(("result", "availability")):
            del session_state[key]  # type: ignore[index]
