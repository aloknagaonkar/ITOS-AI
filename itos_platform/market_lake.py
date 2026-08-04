"""Persistent, point-in-time Historical Market Lake (Sprint 18.4C).

The local backend deliberately uses atomic JSON documents.  Pandas does not ship a
Parquet engine, and adding one solely for the lake would make the application much
heavier.  Files remain typed, versioned, date partitioned, and can be migrated to a
Parquet implementation behind :class:`HistoricalMarketLake` later.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
import hashlib
import json
import os
import re
import tempfile

import pandas as pd

from .replay import DataMode, ReplayRequest, ReplaySettings, normalize_candles, normalize_timestamp


class PeriodPreset(str, Enum):
    WEEK = "WEEK"
    MONTH = "MONTH"
    THREE_MONTHS = "THREE_MONTHS"
    SIX_MONTHS = "SIX_MONTHS"
    ONE_YEAR = "ONE_YEAR"
    CUSTOM = "CUSTOM"


QUALITY_FLAGS = frozenset({
    "RAW_DATA_MISSING", "RAW_DATA_INCOMPLETE", "OPTIONS_UNAVAILABLE", "OPTIONS_PARTIAL",
    "INTELLIGENCE_INCOMPLETE", "OUTCOMES_INCOMPLETE", "SCHEMA_MISMATCH",
    "ENGINE_VERSION_MISMATCH", "DATASET_CORRUPT", "CHECKPOINT_RECOVERED",
    "ENRICHMENT_FAILED", "NO_LOOK_AHEAD_VIOLATION", "DATE_NOT_TRADING_SESSION",
})


@dataclass(frozen=True)
class MarketLakeSettings:
    market_lake_enabled: bool = True
    market_lake_root: Path = Path("data/market_lake")
    raw_schema_version: str = "raw-v1"
    intelligence_schema_version: str = "intelligence-v1"
    outcome_schema_version: str = "outcome-v1"
    engine_version: str = "itos-18.4c-v1"
    default_historical_period: PeriodPreset = PeriodPreset.WEEK
    supported_periods: tuple[PeriodPreset, ...] = tuple(PeriodPreset)
    default_analysis_cadence_minutes: int = 5
    supported_analysis_cadences: tuple[int, ...] = (1, 3, 5, 10, 15, 30, 60)
    checkpoint_interval: int = 10
    raw_retention: str = "indefinite"
    manifest_filename: str = "dataset_manifest.json"
    outcome_horizons: tuple[int, ...] = (5, 15, 30, 60)
    rebuild_on_engine_change: bool = True
    option_storage_enabled: bool = True
    maximum_sync_range: int = 366
    storage_format: str = "typed-json"
    corruption_policy: str = "quarantine-and-report"
    supported_intervals: tuple[int, ...] = (1, 3, 5, 10, 15, 30, 60)


@dataclass(frozen=True)
class HistoricalRangeRequest:
    underlying: str
    instrument_key: str
    start_date: date
    end_date: date
    interval_minutes: int = 1
    expiry_mode: str | None = None
    include_options: bool = True
    rebuild_raw: bool = False
    rebuild_intelligence: bool = False
    rebuild_outcomes: bool = False
    rebuild_options: bool = False

    def validate(self, settings: MarketLakeSettings = MarketLakeSettings(), *, today: date | None = None) -> None:
        if not self.underlying.strip() or not self.instrument_key.strip():
            raise ValueError("supported instrument and underlying are required")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if self.end_date > (today or date.today()):
            raise ValueError("historical range cannot include a future date")
        if self.interval_minutes not in settings.supported_intervals:
            raise ValueError(f"unsupported interval: {self.interval_minutes}")
        if (self.end_date - self.start_date).days + 1 > settings.maximum_sync_range:
            raise ValueError("historical range exceeds maximum_sync_range")
        if not settings.market_lake_enabled:
            raise ValueError("Historical Market Lake provider is unavailable")


def resolve_period(preset: PeriodPreset, end: date, *, custom_start: date | None = None) -> tuple[date, date]:
    if preset is PeriodPreset.CUSTOM:
        if custom_start is None or custom_start > end:
            raise ValueError("CUSTOM requires a valid custom_start")
        return custom_start, end
    days = {PeriodPreset.WEEK: 7, PeriodPreset.MONTH: 30, PeriodPreset.THREE_MONTHS: 90,
            PeriodPreset.SIX_MONTHS: 180, PeriodPreset.ONE_YEAR: 365}[preset]
    return end - timedelta(days=days - 1), end


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    provider: str
    instrument_key: str
    underlying: str
    interval_minutes: int
    analysis_cadence_minutes: int
    start_date: date | None = None
    end_date: date | None = None
    raw_schema_version: str = "raw-v1"
    intelligence_schema_version: str = "intelligence-v1"
    outcome_schema_version: str = "outcome-v1"
    engine_version: str = "itos-18.4c-v1"
    available_dates: tuple[date, ...] = ()
    incomplete_dates: tuple[date, ...] = ()
    failed_dates: tuple[date, ...] = ()
    no_data_dates: tuple[date, ...] = ()
    option_dates: tuple[date, ...] = ()
    option_partial_dates: tuple[date, ...] = ()
    option_unavailable_dates: tuple[date, ...] = ()
    intelligence_dates: tuple[date, ...] = ()
    outcome_dates: tuple[date, ...] = ()
    raw_record_count: int = 0
    intelligence_record_count: int = 0
    outcome_record_count: int = 0
    last_ingested_at: datetime | None = None
    last_enriched_at: datetime | None = None
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalIntelligenceRecord:
    provider: str
    instrument_key: str
    underlying: str
    interval_minutes: int
    trading_date: date
    analysis_timestamp: datetime
    data_cutoff_timestamp: datetime
    latest_completed_candle_timestamp: datetime
    engine_version: str
    schema_version: str
    replay_completeness: str
    recommendation: str = "WAIT"
    recommendation_confidence: float | None = None
    decision_confidence: float | None = None
    decision_confidence_grade: str | None = None
    market_bias: str | None = None
    positioning_state: str | None = None
    compression_state: str | None = None
    manipulation_state: str | None = None
    ranking_eligibility: bool = False
    quality_flags: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    missing_confirmations: tuple[str, ...] = ()
    values: Mapping[str, Any] = field(default_factory=dict, compare=True)

    @property
    def record_id(self) -> str:
        return f"{self.instrument_key}|{self.interval_minutes}|{self.analysis_timestamp.isoformat()}|{self.engine_version}"

    @property
    def trade_id(self) -> str:
        """Stable additive identity used by the historical intelligence index."""
        canonical = "|".join((self.provider, self.instrument_key, self.underlying,
                              str(self.interval_minutes), self.analysis_timestamp.isoformat(),
                              self.engine_version, self.schema_version))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20].upper()
        readable = re.sub(r"[^A-Z0-9]", "", self.underlying.upper())[:12] or "UNKNOWN"
        return f"HTR-{readable}-{self.analysis_timestamp:%Y%m%d-%H%M%S}-{self.interval_minutes}M-{digest}"


@dataclass(frozen=True)
class HistoricalOutcomeRecord:
    intelligence_record_id: str
    instrument_key: str
    interval_minutes: int
    trading_date: date
    analysis_timestamp: datetime
    engine_version: str
    schema_version: str
    reference_price: float
    horizon_prices: tuple[tuple[int, float | None], ...]
    horizon_point_changes: tuple[tuple[int, float | None], ...]
    horizon_percentage_changes: tuple[tuple[int, float | None], ...]
    end_of_session_price: float | None
    maximum_favourable_excursion: float | None
    maximum_adverse_excursion: float | None
    future_data_available: bool
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntelligenceQuery:
    instrument_key: str
    start_date: date
    end_date: date
    interval_minutes: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    recommendation: str | None = None
    market_bias: str | None = None
    positioning_state: str | None = None
    compression_state: str | None = None
    manipulation_state: str | None = None
    minimum_confidence: float | None = None
    maximum_confidence: float | None = None
    ranking_eligibility: bool | None = None
    replay_completeness: str | None = None
    engine_version: str | None = None
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalAvailability:
    requested_start: date
    requested_end: date
    expected_sessions: int
    raw_complete_sessions: int
    intelligence_complete_sessions: int
    outcome_complete_sessions: int
    option_complete_sessions: int
    missing_raw_dates: tuple[date, ...]
    missing_intelligence_dates: tuple[date, ...]
    missing_outcome_dates: tuple[date, ...]
    completeness_percent: float
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncResult:
    completed_dates: tuple[date, ...] = ()
    skipped_dates: tuple[date, ...] = ()
    failed_dates: tuple[date, ...] = ()
    no_data_dates: tuple[date, ...] = ()
    failure_reasons: tuple[tuple[date, str], ...] = ()


class HistoricalMarketLake(Protocol):
    def store_raw_candles(self, provider: str, instrument_key: str, interval: int, day: date, frame: pd.DataFrame) -> None: ...
    def load_raw_candles(self, provider: str, instrument_key: str, interval: int, day: date) -> pd.DataFrame | None: ...
    def store_option_snapshots(self, provider: str, instrument_key: str, expiry: date, day: date, timestamp: datetime, records: Sequence[Mapping[str, Any]]) -> None: ...
    def load_option_snapshots(self, provider: str, instrument_key: str, expiry: date, day: date) -> tuple[Mapping[str, Any], ...]: ...
    def store_intelligence_records(self, records: Sequence[HistoricalIntelligenceRecord]) -> None: ...
    def query_intelligence(self, query: IntelligenceQuery) -> tuple[HistoricalIntelligenceRecord, ...]: ...
    def store_outcomes(self, records: Sequence[HistoricalOutcomeRecord]) -> None: ...
    def query_outcomes(self, instrument_key: str, start_date: date, end_date: date, engine_version: str) -> tuple[HistoricalOutcomeRecord, ...]: ...
    def get_manifest(self, provider: str, instrument_key: str, interval: int) -> DatasetManifest | None: ...


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


_EXCLUDED = object()
_RUNTIME_KEYS = frozenset({"replay_metadata", "market_snapshot", "provider", "client"})


def _json_value(value: Any, *, _seen: set[int] | None = None,
                exclude_runtime_keys: bool = False,
                redact_secret_keys: bool = True) -> Any:
    """Return deterministic JSON data using an explicit serialization policy.

    Typed persistence preserves identity fields. Dashboard callers opt into runtime
    key exclusion. Unknown objects are never stringified because their repr often
    contains memory addresses or credentials; secrets are redacted in both modes.
    """
    seen = _seen if _seen is not None else set()
    if value is None or isinstance(value, (str, int, bool)): return value
    if isinstance(value, float): return None if pd.isna(value) else value
    if isinstance(value, (datetime, date, pd.Timestamp)): return value.isoformat()
    if isinstance(value, Enum):
        return _json_value(value.value, _seen=seen, exclude_runtime_keys=exclude_runtime_keys,
                           redact_secret_keys=redact_secret_keys)
    if callable(value) or isinstance(value, (pd.DataFrame, pd.Series)): return _EXCLUDED
    identity = id(value)
    if identity in seen: return _EXCLUDED
    if isinstance(value, Mapping):
        seen.add(identity)
        result = {}
        for key in sorted(value, key=lambda item: str(item)):
            if _excluded_key(key, exclude_runtime_keys=exclude_runtime_keys,
                             redact_secret_keys=redact_secret_keys): continue
            normalized = _json_value(value[key], _seen=seen,
                                     exclude_runtime_keys=exclude_runtime_keys,
                                     redact_secret_keys=redact_secret_keys)
            if normalized is not _EXCLUDED: result[str(key)] = normalized
        seen.discard(identity)
        return result
    if isinstance(value, (tuple, list)):
        seen.add(identity)
        result = [_json_value(item, _seen=seen, exclude_runtime_keys=exclude_runtime_keys,
                              redact_secret_keys=redact_secret_keys) for item in value]
        seen.discard(identity)
        return [item for item in result if item is not _EXCLUDED]
    if is_dataclass(value):
        return _json_value(asdict(value), _seen=seen, exclude_runtime_keys=exclude_runtime_keys,
                           redact_secret_keys=redact_secret_keys)
    if hasattr(value, "item"):
        try:
            return _json_value(value.item(), _seen=seen, exclude_runtime_keys=exclude_runtime_keys,
                               redact_secret_keys=redact_secret_keys)
        except (ValueError, TypeError): return _EXCLUDED
    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, Mapping):
        return _json_value({key: item for key, item in attributes.items()
                            if not str(key).startswith("_")}, _seen=seen,
                           exclude_runtime_keys=exclude_runtime_keys,
                           redact_secret_keys=redact_secret_keys)
    return _EXCLUDED


def _secret(key: Any) -> bool:
    lowered = str(key).lower().replace("-", "_")
    return any(word in lowered for word in (
        "token", "secret", "authorization", "api_key", "account_id", "credential", "password",
    ))


def _excluded_key(key: Any, *, exclude_runtime_keys: bool = False,
                  redact_secret_keys: bool = True) -> bool:
    lowered = str(key).lower().replace("-", "_")
    return (lowered.startswith("_")
            or exclude_runtime_keys and lowered in _RUNTIME_KEYS
            or redact_secret_keys and _secret(lowered))


def _field(value: Any, name: str, default: Any = None) -> Any:
    """Read metadata represented as either a mapping or an attribute object."""
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _result_values(result: Any) -> dict[str, Any]:
    """Extract a runner result without constraining adapters to plain dictionaries."""
    if isinstance(result, Mapping): return dict(result)
    values = getattr(result, "values", None)
    if isinstance(values, Mapping): return dict(values)
    if is_dataclass(result): return asdict(result)
    attributes = getattr(result, "__dict__", None)
    if isinstance(attributes, Mapping):
        return {str(key): value for key, value in attributes.items() if not str(key).startswith("_")}
    raise TypeError("dashboard result has no serializable public values")


def _safe_failure_reason(error: Exception) -> str:
    """Diagnostic classification without persisting exception text or secrets."""
    if str(error) == "NO_LOOK_AHEAD_VIOLATION": return "NO_LOOK_AHEAD_VIOLATION"
    return f"{type(error).__name__}: historical enrichment point failed"


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            normalized = _json_value(payload)
            if normalized is _EXCLUDED: raise TypeError("payload is not serializable market-lake data")
            json.dump(normalized, stream, separators=(",", ":"), sort_keys=True, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class LocalHistoricalMarketLake:
    """Date-partitioned local store with atomic writes and deterministic upserts."""
    def __init__(self, settings: MarketLakeSettings = MarketLakeSettings()) -> None:
        self.settings = settings
        self.root = Path(settings.market_lake_root)

    def _raw_path(self, provider: str, instrument: str, interval: int, day: date) -> Path:
        return self.root / "raw/candles" / _safe(provider) / _safe(instrument) / str(interval) / str(day.year) / f"{day}.json"

    def store_raw_candles(self, provider: str, instrument_key: str, interval: int, day: date, frame: pd.DataFrame) -> None:
        normalized, invalid, duplicates = normalize_candles(frame)
        if normalized.empty: raise ValueError("raw candle dataset is empty or malformed")
        if any(normalize_timestamp(v).date() != day for v in normalized["timestamp"]):
            raise ValueError("raw dataset contains candles outside its partition date")
        payload = {"schema_version": self.settings.raw_schema_version, "invalid_rows": invalid,
                   "duplicate_timestamps": duplicates, "records": normalized.to_dict("records")}
        _atomic_json(self._raw_path(provider, instrument_key, interval, day), payload)

    def load_raw_candles(self, provider: str, instrument_key: str, interval: int, day: date) -> pd.DataFrame | None:
        try:
            payload = json.loads(self._raw_path(provider, instrument_key, interval, day).read_text())
            if payload["schema_version"] != self.settings.raw_schema_version: return None
            return pd.DataFrame(payload["records"]).copy(deep=True)
        except (OSError, ValueError, TypeError, KeyError): return None

    def store_normalized(self, instrument_key: str, interval: int, day: date, frame: pd.DataFrame) -> None:
        normalized, invalid, duplicates = normalize_candles(frame)
        path = self.root / "normalized" / _safe(instrument_key) / str(interval) / f"{day}.json"
        _atomic_json(path, {"schema_version": self.settings.raw_schema_version, "invalid_rows": invalid,
                            "duplicate_timestamps": duplicates, "records": normalized.to_dict("records")})

    def store_option_snapshots(self, provider: str, instrument_key: str, expiry: date, day: date,
                               timestamp: datetime, records: Sequence[Mapping[str, Any]]) -> None:
        if not self.settings.option_storage_enabled: raise ValueError("option storage is disabled")
        path = self.root / "raw/options" / _safe(provider) / _safe(instrument_key) / str(expiry) / str(day) / f"{_safe(timestamp.isoformat())}.json"
        _atomic_json(path, {"schema_version": self.settings.raw_schema_version, "source_timestamp": timestamp,
                            "ingested_at": datetime.now(timezone.utc), "records": list(records)})

    def load_option_snapshots(self, provider: str, instrument_key: str, expiry: date, day: date) -> tuple[Mapping[str, Any], ...]:
        folder = self.root / "raw/options" / _safe(provider) / _safe(instrument_key) / str(expiry) / str(day)
        rows: list[Mapping[str, Any]] = []
        try:
            for path in sorted(folder.glob("*.json")): rows.extend(json.loads(path.read_text())["records"])
        except (OSError, ValueError, TypeError, KeyError): return ()
        return tuple(dict(row) for row in rows)

    def _records_path(self, layer: str, engine: str, instrument: str, interval: int, day: date) -> Path:
        return self.root / layer / _safe(engine) / _safe(instrument) / str(interval) / f"{day}.json"

    def store_intelligence_records(self, records: Sequence[HistoricalIntelligenceRecord]) -> None:
        for group in _group(records, lambda r: (r.engine_version, r.instrument_key, r.interval_minutes, r.trading_date)):
            sample = group[0]; path = self._records_path("intelligence", sample.engine_version, sample.instrument_key, sample.interval_minutes, sample.trading_date)
            existing = {r.record_id: r for r in self._read_intelligence(path)}
            existing.update({r.record_id: r for r in group})
            _atomic_json(path, {"schema_version": self.settings.intelligence_schema_version,
                                "records": [asdict(v) for _, v in sorted(existing.items())]})

    def _read_intelligence(self, path: Path) -> tuple[HistoricalIntelligenceRecord, ...]:
        try:
            payload = json.loads(path.read_text())
            if payload["schema_version"] != self.settings.intelligence_schema_version: return ()
            return tuple(_intelligence_from_dict(v) for v in payload["records"])
        except (OSError, ValueError, TypeError, KeyError): return ()

    def query_intelligence(self, query: IntelligenceQuery) -> tuple[HistoricalIntelligenceRecord, ...]:
        engines = [_safe(query.engine_version)] if query.engine_version else [p.name for p in (self.root / "intelligence").glob("*") if p.is_dir()]
        records: list[HistoricalIntelligenceRecord] = []
        for engine in engines:
            base = self.root / "intelligence" / engine / _safe(query.instrument_key)
            intervals = [str(query.interval_minutes)] if query.interval_minutes else [p.name for p in base.glob("*") if p.is_dir()]
            for interval in intervals:
                day = query.start_date
                while day <= query.end_date:
                    records.extend(self._read_intelligence(base / interval / f"{day}.json")); day += timedelta(days=1)
        def matches(r: HistoricalIntelligenceRecord) -> bool:
            confidence = r.decision_confidence
            return ((query.start_time is None or r.analysis_timestamp.time() >= query.start_time)
                    and (query.end_time is None or r.analysis_timestamp.time() <= query.end_time)
                    and all(getattr(r, name) == value for name, value in (("recommendation", query.recommendation), ("market_bias", query.market_bias),
                        ("positioning_state", query.positioning_state), ("compression_state", query.compression_state),
                        ("manipulation_state", query.manipulation_state), ("ranking_eligibility", query.ranking_eligibility),
                        ("replay_completeness", query.replay_completeness)) if value is not None)
                    and (query.minimum_confidence is None or confidence is not None and confidence >= query.minimum_confidence)
                    and (query.maximum_confidence is None or confidence is not None and confidence <= query.maximum_confidence)
                    and set(query.quality_flags).issubset(r.quality_flags))
        return tuple(replace(r, values=dict(r.values)) for r in sorted(filter(matches, records), key=lambda v: v.analysis_timestamp))

    def store_outcomes(self, records: Sequence[HistoricalOutcomeRecord]) -> None:
        for group in _group(records, lambda r: (r.engine_version, r.instrument_key, r.interval_minutes, r.trading_date)):
            sample = group[0]; path = self._records_path("outcomes", sample.engine_version, sample.instrument_key, sample.interval_minutes, sample.trading_date)
            existing = {r.intelligence_record_id: r for r in self._read_outcomes(path)}
            existing.update({r.intelligence_record_id: r for r in group})
            _atomic_json(path, {"schema_version": self.settings.outcome_schema_version, "records": [asdict(v) for _, v in sorted(existing.items())]})

    def _read_outcomes(self, path: Path) -> tuple[HistoricalOutcomeRecord, ...]:
        try:
            payload = json.loads(path.read_text())
            if payload["schema_version"] != self.settings.outcome_schema_version: return ()
            return tuple(_outcome_from_dict(v) for v in payload["records"])
        except (OSError, ValueError, TypeError, KeyError): return ()

    def query_outcomes(self, instrument_key: str, start_date: date, end_date: date, engine_version: str) -> tuple[HistoricalOutcomeRecord, ...]:
        result = []
        base = self.root / "outcomes" / _safe(engine_version) / _safe(instrument_key)
        for interval in base.glob("*"):
            day = start_date
            while day <= end_date:
                result.extend(self._read_outcomes(interval / f"{day}.json")); day += timedelta(days=1)
        return tuple(result)

    def _manifest_path(self, provider: str, instrument: str, interval: int) -> Path:
        return self.root / "manifest" / _safe(provider) / _safe(instrument) / str(interval) / self.settings.manifest_filename

    def get_manifest(self, provider: str, instrument_key: str, interval: int) -> DatasetManifest | None:
        try: return _manifest_from_dict(json.loads(self._manifest_path(provider, instrument_key, interval).read_text()))
        except (OSError, ValueError, TypeError, KeyError): return None

    def put_manifest(self, manifest: DatasetManifest) -> None:
        _atomic_json(self._manifest_path(manifest.provider, manifest.instrument_key, manifest.interval_minutes), asdict(manifest))


    def option_download_status(self, provider: str, instrument_key: str, interval: int, day: date) -> str | None:
        """Return the durable terminal option-download state for a trading date."""
        manifest = self.get_manifest(provider, instrument_key, interval)
        if manifest is None:
            return None
        if day in set(manifest.option_partial_dates) or day in set(manifest.option_dates):
            return "PARTIAL"
        if day in set(manifest.option_unavailable_dates):
            return "UNAVAILABLE"
        return None

    def mark_option_download_status(
        self, provider: str, instrument_key: str, underlying: str, interval: int,
        day: date, status: str,
    ) -> None:
        """Persist an option-download terminal state without overwriting raw-data state."""
        manifest = self.get_manifest(provider, instrument_key, interval)
        if manifest is None:
            manifest = DatasetManifest(
                dataset_id=f"{_safe(provider)}-{_safe(instrument_key)}-{interval}",
                provider=provider, instrument_key=instrument_key, underlying=underlying,
                interval_minutes=interval,
                analysis_cadence_minutes=self.settings.default_analysis_cadence_minutes,
                raw_schema_version=self.settings.raw_schema_version,
                intelligence_schema_version=self.settings.intelligence_schema_version,
                outcome_schema_version=self.settings.outcome_schema_version,
                engine_version=self.settings.engine_version,
            )
        partial = set(manifest.option_partial_dates)
        available = set(manifest.option_dates)
        unavailable = set(manifest.option_unavailable_dates)
        if status == "PARTIAL":
            partial.add(day); available.add(day); unavailable.discard(day)
        elif status == "UNAVAILABLE":
            unavailable.add(day); partial.discard(day); available.discard(day)
        else:
            raise ValueError(f"unsupported option download status: {status}")
        self.put_manifest(replace(
            manifest, option_dates=tuple(sorted(available)),
            option_partial_dates=tuple(sorted(partial)),
            option_unavailable_dates=tuple(sorted(unavailable)),
        ))

    def list_available_dates(self, provider: str, instrument_key: str, interval: int) -> tuple[date, ...]:
        manifest = self.get_manifest(provider, instrument_key, interval); return manifest.available_dates if manifest else ()

    def find_missing_dates(self, provider: str, instrument_key: str, interval: int, expected: Iterable[date]) -> tuple[date, ...]:
        complete = set(self.list_available_dates(provider, instrument_key, interval)); return tuple(d for d in expected if d not in complete)


def _group(items: Sequence[Any], key: Callable[[Any], Any]) -> list[list[Any]]:
    groups: dict[Any, list[Any]] = {}
    for item in items: groups.setdefault(key(item), []).append(item)
    return list(groups.values())


def _intelligence_from_dict(value: Mapping[str, Any]) -> HistoricalIntelligenceRecord:
    data = dict(value)
    for key in ("trading_date",): data[key] = date.fromisoformat(data[key])
    for key in ("analysis_timestamp", "data_cutoff_timestamp", "latest_completed_candle_timestamp"): data[key] = datetime.fromisoformat(data[key])
    for key in ("quality_flags", "blockers", "missing_confirmations"): data[key] = tuple(data.get(key, ()))
    return HistoricalIntelligenceRecord(**data)


def _outcome_from_dict(value: Mapping[str, Any]) -> HistoricalOutcomeRecord:
    data = dict(value); data["trading_date"] = date.fromisoformat(data["trading_date"]); data["analysis_timestamp"] = datetime.fromisoformat(data["analysis_timestamp"])
    for key in ("horizon_prices", "horizon_point_changes", "horizon_percentage_changes"): data[key] = tuple((int(k), v) for k, v in data[key])
    data["quality_flags"] = tuple(data.get("quality_flags", ())); return HistoricalOutcomeRecord(**data)


def _manifest_from_dict(value: Mapping[str, Any]) -> DatasetManifest:
    data = dict(value)
    for key in ("start_date", "end_date"): data[key] = date.fromisoformat(data[key]) if data.get(key) else None
    for key in ("available_dates", "incomplete_dates", "failed_dates", "no_data_dates", "option_dates", "option_partial_dates", "option_unavailable_dates", "intelligence_dates", "outcome_dates"): data[key] = tuple(date.fromisoformat(v) for v in data.get(key, ()))
    for key in ("last_ingested_at", "last_enriched_at"): data[key] = datetime.fromisoformat(data[key]) if data.get(key) else None
    for key in ("quality_flags", "explanations"): data[key] = tuple(data.get(key, ()))
    return DatasetManifest(**data)


def new_manifest(request: HistoricalRangeRequest, provider: str, settings: MarketLakeSettings) -> DatasetManifest:
    return DatasetManifest(dataset_id=f"{_safe(provider)}-{_safe(request.instrument_key)}-{request.interval_minutes}", provider=provider,
        instrument_key=request.instrument_key, underlying=request.underlying, interval_minutes=request.interval_minutes,
        analysis_cadence_minutes=settings.default_analysis_cadence_minutes, raw_schema_version=settings.raw_schema_version,
        intelligence_schema_version=settings.intelligence_schema_version, outcome_schema_version=settings.outcome_schema_version,
        engine_version=settings.engine_version)


class HistoricalIngestionService:
    """Sequential, failure-isolated sync. Fetcher is historical-only by contract."""
    def __init__(self, lake: LocalHistoricalMarketLake, fetcher: Callable[[HistoricalRangeRequest, date], pd.DataFrame], *, provider: str) -> None:
        self.lake, self.fetcher, self.provider = lake, fetcher, provider

    def synchronize(self, request: HistoricalRangeRequest, expected_dates: Sequence[date], progress: Callable[[date, str], None] | None = None) -> SyncResult:
        request.validate(self.lake.settings); progress = progress or (lambda _d, _s: None)
        manifest = self.lake.get_manifest(self.provider, request.instrument_key, request.interval_minutes) or new_manifest(request, self.provider, self.lake.settings)
        completed, skipped, failed, no_data = [], [], [], []
        available = set(manifest.available_dates); failures = set(manifest.failed_dates); absent = set(manifest.no_data_dates)
        for day in expected_dates:
            if day in available and not request.rebuild_raw: skipped.append(day); progress(day, "skipped"); continue
            try:
                frame = self.fetcher(request, day)
                if not isinstance(frame, pd.DataFrame) or frame.empty:
                    absent.add(day); failures.discard(day); no_data.append(day); progress(day, "no-data"); continue
                self.lake.store_raw_candles(self.provider, request.instrument_key, request.interval_minutes, day, frame)
                self.lake.store_normalized(request.instrument_key, request.interval_minutes, day, frame)
                available.add(day); failures.discard(day); absent.discard(day); completed.append(day); progress(day, "completed")
            except Exception:
                failures.add(day); failed.append(day); progress(day, "failed")
        all_dates = sorted(available)
        updated = replace(manifest, start_date=min(all_dates) if all_dates else manifest.start_date,
            end_date=max(all_dates) if all_dates else manifest.end_date, available_dates=tuple(all_dates), failed_dates=tuple(sorted(failures)),
            no_data_dates=tuple(sorted(absent)), raw_record_count=sum(len(frame) if frame is not None else 0 for d in all_dates
                for frame in (self.lake.load_raw_candles(self.provider, request.instrument_key, request.interval_minutes, d),)),
            last_ingested_at=datetime.now(timezone.utc), quality_flags=tuple(sorted(set(manifest.quality_flags) | ({"DATE_NOT_TRADING_SESSION"} if absent else set()))))
        self.lake.put_manifest(updated)
        return SyncResult(tuple(completed), tuple(skipped), tuple(failed), tuple(no_data))


class HistoricalEnrichmentService:
    """Runs the injected existing replay/dashboard pipeline at fresh cutoff points."""
    def __init__(self, lake: LocalHistoricalMarketLake, runner: Callable[[ReplayRequest], Any], *, provider: str) -> None:
        self.lake, self.runner, self.provider = lake, runner, provider

    def enrich(self, request: HistoricalRangeRequest, days: Sequence[date], *, cadence_minutes: int | None = None,
               progress: Callable[[date, str], None] | None = None) -> SyncResult:
        cadence = cadence_minutes or self.lake.settings.default_analysis_cadence_minutes
        if cadence not in self.lake.settings.supported_analysis_cadences: raise ValueError("unsupported analysis cadence")
        progress = progress or (lambda _d, _s: None); done, failed, failure_reasons = [], [], []
        existing = self.lake.query_intelligence(IntelligenceQuery(request.instrument_key, request.start_date, request.end_date,
            request.interval_minutes, engine_version=self.lake.settings.engine_version))
        existing_ids = {r.record_id for r in existing}
        for day in days:
            frame = self.lake.load_raw_candles(self.provider, request.instrument_key, request.interval_minutes, day)
            if frame is None: failed.append(day); progress(day, "raw-missing"); continue
            normalized, _, _ = normalize_candles(frame); records = []
            try:
                for index, row in normalized.iterrows():
                    if index % max(1, cadence // request.interval_minutes): continue
                    stamp = normalize_timestamp(row["timestamp"]).to_pydatetime()
                    replay = ReplayRequest(request.underlying, request.instrument_key, day, stamp, request.interval_minutes,
                                           requested_option_snapshot=request.include_options)
                    identity = f"{request.instrument_key}|{request.interval_minutes}|{stamp.isoformat()}|{self.lake.settings.engine_version}"
                    if identity in existing_ids and not request.rebuild_intelligence: continue
                    result = self.runner(replay)  # a new runner invocation/context for every point
                    record = serialize_dashboard_result(result, replay, self.provider, self.lake.settings)
                    if record.latest_completed_candle_timestamp > record.data_cutoff_timestamp:
                        raise ValueError("NO_LOOK_AHEAD_VIOLATION")
                    records.append(record); existing_ids.add(record.record_id)
                    if len(records) >= self.lake.settings.checkpoint_interval:
                        self.lake.store_intelligence_records(records); records.clear()
                self.lake.store_intelligence_records(records); done.append(day); progress(day, "completed")
            except Exception as error:
                reason = _safe_failure_reason(error)
                failed.append(day); failure_reasons.append((day, reason)); progress(day, f"failed: {reason}")
        return SyncResult(tuple(done), (), tuple(failed), (), tuple(failure_reasons))


def serialize_dashboard_result(result: Any, request: ReplayRequest, provider: str, settings: MarketLakeSettings) -> HistoricalIntelligenceRecord:
    values = _result_values(result)
    metadata = values.get("replay_metadata") or _field(values.get("market_snapshot"), "replay_metadata")
    cutoff = _field(metadata, "data_cutoff_timestamp") or request.replay_timestamp
    latest = _field(metadata, "latest_candle_timestamp") or cutoff
    if normalize_timestamp(latest) > normalize_timestamp(cutoff): raise ValueError("NO_LOOK_AHEAD_VIOLATION")
    recommendation = values.get("recommendation") or {}; confidence = values.get("decision_confidence")
    ranking = values.get("trade_opportunity_ranking"); compression = values.get("compression_intelligence")
    positioning = values.get("positioning_intelligence"); manipulation = values.get("manipulation_intelligence")
    serial = _json_value(values, exclude_runtime_keys=True)
    if not isinstance(serial, dict): raise TypeError("dashboard result did not produce a JSON object")
    return HistoricalIntelligenceRecord(provider, request.instrument_key, request.underlying, request.interval_minutes,
        request.trading_date, request.replay_timestamp, normalize_timestamp(cutoff).to_pydatetime(), normalize_timestamp(latest).to_pydatetime(),
        settings.engine_version, settings.intelligence_schema_version, getattr(_field(metadata, "replay_completeness", "UNAVAILABLE"), "value", _field(metadata, "replay_completeness", "UNAVAILABLE")),
        recommendation=str(recommendation.get("side", "WAIT")) if isinstance(recommendation, Mapping) else str(recommendation),
        recommendation_confidence=recommendation.get("confidence") if isinstance(recommendation, Mapping) else None,
        decision_confidence=getattr(confidence, "score", confidence if isinstance(confidence, (int, float)) else None),
        decision_confidence_grade=getattr(confidence, "grade", None), market_bias=serial.get("market_bias"),
        positioning_state=getattr(positioning, "state", None), compression_state=getattr(compression, "state", None),
        manipulation_state=getattr(manipulation, "state", None), ranking_eligibility=bool(getattr(ranking, "eligible", False)),
        quality_flags=tuple(_field(metadata, "quality_flags", ())), blockers=tuple(recommendation.get("blockers", ())) if isinstance(recommendation, Mapping) else (), values=serial)


class HistoricalOutcomeService:
    """Factual future-price enrichment, intentionally independent of the pipeline."""
    def __init__(self, lake: LocalHistoricalMarketLake, *, provider: str) -> None: self.lake, self.provider = lake, provider

    def build(self, records: Sequence[HistoricalIntelligenceRecord]) -> tuple[HistoricalOutcomeRecord, ...]:
        outcomes = []
        for record in records:
            candles = self.lake.load_raw_candles(self.provider, record.instrument_key, record.interval_minutes, record.trading_date)
            normalized, _, _ = normalize_candles(candles) if candles is not None else (pd.DataFrame(), 0, 0)
            future = normalized[normalized["timestamp"].map(normalize_timestamp) > normalize_timestamp(record.data_cutoff_timestamp)] if not normalized.empty else normalized
            at_or_before = normalized[normalized["timestamp"].map(normalize_timestamp) <= normalize_timestamp(record.data_cutoff_timestamp)] if not normalized.empty else normalized
            if at_or_before.empty: continue
            reference = float(at_or_before.iloc[-1]["close"]); prices = []
            for horizon in self.lake.settings.outcome_horizons:
                target = normalize_timestamp(record.analysis_timestamp) + pd.Timedelta(minutes=horizon)
                candidates = future[future["timestamp"].map(normalize_timestamp) >= target]
                prices.append((horizon, None if candidates.empty else float(candidates.iloc[0]["close"])))
            changes = tuple((h, None if p is None else p-reference) for h, p in prices)
            percentages = tuple((h, None if p is None or reference == 0 else (p-reference)/reference*100) for h, p in prices)
            outcomes.append(HistoricalOutcomeRecord(record.record_id, record.instrument_key, record.interval_minutes, record.trading_date,
                record.analysis_timestamp, record.engine_version, self.lake.settings.outcome_schema_version, reference, tuple(prices), changes, percentages,
                None if future.empty else float(future.iloc[-1]["close"]), None if future.empty else float(future["high"].max()-reference),
                None if future.empty else float(future["low"].min()-reference), not future.empty,
                () if not future.empty else ("OUTCOMES_INCOMPLETE",)))
        self.lake.store_outcomes(outcomes); return tuple(outcomes)


def availability(manifest: DatasetManifest, expected_dates: Sequence[date]) -> HistoricalAvailability:
    expected = tuple(dict.fromkeys(expected_dates)); raw, intel, outcomes, options = map(set, (manifest.available_dates, manifest.intelligence_dates, manifest.outcome_dates, manifest.option_dates))
    missing_raw = tuple(d for d in expected if d not in raw); missing_intel = tuple(d for d in expected if d not in intel); missing_outcomes = tuple(d for d in expected if d not in outcomes)
    denominator = max(1, len(expected) * 3); percentage = min(100.0, max(0.0, 100.0 * (len(raw & set(expected)) + len(intel & set(expected)) + len(outcomes & set(expected))) / denominator))
    flags = tuple(flag for flag, missing in (("RAW_DATA_MISSING", missing_raw), ("INTELLIGENCE_INCOMPLETE", missing_intel), ("OUTCOMES_INCOMPLETE", missing_outcomes)) if missing)
    return HistoricalAvailability(manifest.start_date or (expected[0] if expected else date.min), manifest.end_date or (expected[-1] if expected else date.min), len(expected),
        len(raw & set(expected)), len(intel & set(expected)), len(outcomes & set(expected)), len(options & set(expected)), missing_raw, missing_intel, missing_outcomes, percentage, flags)


@dataclass(frozen=True)
class MarketLakeStatus:
    instrument_key: str
    requested_start: date
    requested_end: date
    interval_minutes: int
    include_options: bool
    engine_version: str
    storage_location: str
    completed_dates: tuple[date, ...]
    failed_dates: tuple[date, ...]
    progress_status: str


class MarketLakeDeveloperService:
    """Minimal CLI/UI-compatible status surface; no analytics aggregation."""
    def __init__(self, lake: LocalHistoricalMarketLake, provider: str) -> None: self.lake, self.provider = lake, provider
    def status(self, request: HistoricalRangeRequest) -> MarketLakeStatus:
        manifest = self.lake.get_manifest(self.provider, request.instrument_key, request.interval_minutes) or new_manifest(request, self.provider, self.lake.settings)
        return MarketLakeStatus(request.instrument_key, request.start_date, request.end_date, request.interval_minutes, request.include_options,
            self.lake.settings.engine_version, str(self.lake.root), manifest.available_dates, manifest.failed_dates, "READY")
