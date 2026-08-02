"""Point-in-time market-data contracts and replay providers (Sprint 18.4A)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from zoneinfo import ZoneInfo
import json

import pandas as pd

from .decision_context import MarketSnapshot

MARKET_TZ = ZoneInfo("Asia/Kolkata")


class DataMode(str, Enum):
    LIVE = "LIVE"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    SAMPLE_DATA = "SAMPLE_DATA"


class ReplayCompleteness(str, Enum):
    FULL_REPLAY = "FULL_REPLAY"
    PARTIAL_OPTION_REPLAY = "PARTIAL_OPTION_REPLAY"
    CANDLE_ONLY_REPLAY = "CANDLE_ONLY_REPLAY"
    SAMPLE_REPLAY = "SAMPLE_REPLAY"
    LIVE = "LIVE"
    UNAVAILABLE = "UNAVAILABLE"


class HistoricalOptionStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_REQUESTED = "NOT_REQUESTED"
    LIVE = "LIVE"


SAMPLE_SCENARIOS = (
    "BULLISH_EXPANSION", "BEARISH_EXPANSION", "RANGE_COMPRESSION",
    "FALSE_BREAKOUT", "FALSE_BREAKDOWN", "ACCUMULATION", "DISTRIBUTION",
    "MISSING_OPTION_DATA", "MALFORMED_CANDLE_DATA",
)


@dataclass(frozen=True)
class ReplaySettings:
    timezone: str = "Asia/Kolkata"
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    supported_intervals: tuple[int, ...] = (1, 3, 5, 10, 15, 30, 60)
    warm_up_sessions: int = 2
    minimum_candles: int = 20
    cache_root: Path = Path("data/historical")
    cache_schema_version: str = "v1"
    cache_enabled: bool = True
    option_tolerance_minutes: int = 15
    exclude_incomplete_candle: bool = True
    filter_replay_history: bool = True


@dataclass(frozen=True)
class ReplayRequest:
    underlying: str
    instrument_key: str
    trading_date: date
    replay_timestamp: datetime
    interval_minutes: int
    expiry: date | None = None
    requested_option_snapshot: bool = True
    sample_scenario: str | None = None

    def validate(self, settings: ReplaySettings = ReplaySettings(), *, sample: bool = False) -> None:
        if not self.underlying.strip() or not self.instrument_key.strip():
            raise ValueError("underlying and instrument_key are required")
        if self.interval_minutes not in settings.supported_intervals:
            raise ValueError(f"unsupported replay interval: {self.interval_minutes}")
        stamp = normalize_timestamp(self.replay_timestamp, settings.timezone)
        if stamp.date() != self.trading_date:
            raise ValueError("replay timestamp must belong to trading_date")
        if not settings.market_open <= stamp.time().replace(tzinfo=None) <= settings.market_close:
            raise ValueError("replay timestamp is outside configured market hours")
        if sample and self.sample_scenario not in SAMPLE_SCENARIOS:
            raise ValueError("SAMPLE_DATA requires an approved sample scenario")


@dataclass(frozen=True)
class ReplayMetadata:
    mode: DataMode
    analysis_timestamp: datetime | None
    data_cutoff_timestamp: datetime | None
    latest_candle_timestamp: datetime | None
    option_snapshot_timestamp: datetime | None
    candle_source: str
    option_source: str | None
    look_ahead_protected: bool
    candles_cutoff_applied: bool
    option_cutoff_applied: bool
    replay_completeness: ReplayCompleteness
    historical_option_status: HistoricalOptionStatus
    future_candle_count_excluded: int = 0
    invalid_row_count: int = 0
    duplicate_row_count: int = 0
    warm_up_candle_count: int = 0
    replay_session_candle_count: int = 0
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


class MarketDataProvider(Protocol):
    mode: DataMode
    def build_market_snapshot(self, *, request: ReplayRequest | None = None,
                              current_context: Mapping[str, object] | None = None) -> MarketSnapshot: ...


class HistoricalOptionSnapshotSource(Protocol):
    def nearest_at_or_before(self, *, instrument_key: str, expiry: date | None,
                             cutoff: datetime) -> tuple[datetime, Mapping[str, Any], HistoricalOptionStatus] | None: ...


def normalize_timestamp(value: Any, timezone: str = "Asia/Kolkata") -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(timezone)
    else:
        stamp = stamp.tz_convert(timezone)
    return stamp


def normalize_candles(frame: pd.DataFrame, timezone: str = "Asia/Kolkata") -> tuple[pd.DataFrame, int, int]:
    """Normalize without mutating source; duplicate rule is stable keep-last."""
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]), 0, 0
    result = frame.copy(deep=True)
    aliases = {"datetime": "timestamp", "date": "timestamp", "time": "timestamp",
               "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "oi": "open_interest"}
    result = result.rename(columns={c: aliases.get(str(c).lower(), str(c).lower()) for c in result.columns})
    before = len(result)
    if "timestamp" not in result:
        return result.iloc[0:0].copy(), before, 0
    # Naive provider values are documented as India time; aware values are converted.
    def parse(value: Any) -> Any:
        try: return normalize_timestamp(value, timezone)
        except (TypeError, ValueError): return pd.NaT
    result["timestamp"] = result["timestamp"].map(parse)
    for column in ("open", "high", "low", "close"):
        if column not in result:
            result[column] = float("nan")
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in ("volume", "open_interest"):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["timestamp", "open", "high", "low", "close"])
    result["timestamp"] = pd.DatetimeIndex(result["timestamp"])
    invalid = before - len(result)
    duplicates = int(result.duplicated("timestamp", keep="last").sum())
    result = result.drop_duplicates("timestamp", keep="last").sort_values("timestamp").reset_index(drop=True)
    return result, invalid, duplicates


def replay_cutoff(stamp: datetime, interval: int, timezone: str = "Asia/Kolkata") -> pd.Timestamp:
    normalized = normalize_timestamp(stamp, timezone)
    return normalized.floor(f"{interval}min")


class CandleCache:
    """Small JSON cache; avoids an optional parquet engine dependency."""
    def __init__(self, settings: ReplaySettings = ReplaySettings()) -> None: self.settings = settings
    def _path(self, source: str, instrument: str, day: date, interval: int) -> Path:
        safe = instrument.replace("|", "_").replace("/", "_")
        return self.settings.cache_root / "candles" / source / safe / str(interval) / self.settings.cache_schema_version / f"{day}.json"
    def read(self, source: str, instrument: str, day: date, interval: int) -> pd.DataFrame | None:
        path = self._path(source, instrument, day, interval)
        try:
            payload = json.loads(path.read_text())
            if payload.get("schema") != self.settings.cache_schema_version: return None
            return pd.DataFrame(payload["records"]).copy(deep=True)
        except (OSError, ValueError, TypeError, KeyError): return None
    def write(self, source: str, instrument: str, day: date, interval: int, frame: pd.DataFrame) -> None:
        path = self._path(source, instrument, day, interval); path.parent.mkdir(parents=True, exist_ok=True)
        records = frame.copy(deep=True).assign(timestamp=lambda x: x["timestamp"].astype(str)).to_dict("records")
        path.write_text(json.dumps({"schema": self.settings.cache_schema_version, "records": records}))


class CachedHistoricalCandleLoader:
    """Read-through loader that never exposes the cache's mutable frame."""

    _required_columns = frozenset({"timestamp", "open", "high", "low", "close"})

    def __init__(self, source_loader: Callable[[ReplayRequest], pd.DataFrame], cache: Any, *,
                 source: str = "historical") -> None:
        self.source_loader = source_loader
        self.cache = cache
        self.source = source

    def __call__(self, request: ReplayRequest) -> pd.DataFrame:
        cached = self.cache.read(
            self.source, request.instrument_key, request.trading_date,
            request.interval_minutes,
        )
        if isinstance(cached, pd.DataFrame) and self._required_columns <= set(cached.columns):
            return cached.copy(deep=True)

        loaded = self.source_loader(request)
        if not isinstance(loaded, pd.DataFrame):
            return pd.DataFrame(columns=sorted(self._required_columns))
        source_copy = loaded.copy(deep=True)
        self.cache.write(
            self.source, request.instrument_key, request.trading_date,
            request.interval_minutes, source_copy,
        )
        return source_copy.copy(deep=True)


class HistoricalCandleDownloader:
    def __init__(self, client: Any, max_days_per_request: int = 30) -> None:
        self.client, self.max_days = client, max_days_per_request
    def download(self, instrument: str, start: date, end: date, interval: int) -> pd.DataFrame:
        frames, cursor = [], start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=self.max_days - 1))
            frames.append(self.client.get_historical_candles(instrument, from_date=cursor.isoformat(), to_date=chunk_end.isoformat(), interval=interval, unit="minutes"))
            cursor = chunk_end + timedelta(days=1)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class HistoricalReplayProvider:
    mode = DataMode.HISTORICAL_REPLAY
    def __init__(self, candle_loader: Callable[[ReplayRequest], pd.DataFrame], *,
                 option_source: HistoricalOptionSnapshotSource | None = None,
                 settings: ReplaySettings = ReplaySettings(), candle_source: str = "historical") -> None:
        self.loader, self.option_source, self.settings, self.candle_source = candle_loader, option_source, settings, candle_source
    def build_market_snapshot(self, *, request: ReplayRequest | None = None, current_context: Mapping[str, object] | None = None) -> MarketSnapshot:
        if request is None: raise ValueError("HISTORICAL_REPLAY requires ReplayRequest")
        request.validate(self.settings)
        analysis = normalize_timestamp(request.replay_timestamp, self.settings.timezone)
        cutoff = replay_cutoff(request.replay_timestamp, request.interval_minutes, self.settings.timezone)
        candles, invalid, duplicates = normalize_candles(self.loader(request), self.settings.timezone)
        # Timestamp denotes candle open: at an exact boundary that candle is not complete.
        included = candles.loc[candles["timestamp"] < cutoff].copy().reset_index(drop=True)
        future = len(candles) - len(included)
        option = None
        if request.requested_option_snapshot and self.option_source:
            option = self.option_source.nearest_at_or_before(instrument_key=request.instrument_key, expiry=request.expiry, cutoff=cutoff.to_pydatetime())
            if option and normalize_timestamp(option[0], self.settings.timezone) > cutoff: option = None
        status = option[2] if option else (HistoricalOptionStatus.NOT_REQUESTED if not request.requested_option_snapshot else HistoricalOptionStatus.UNAVAILABLE)
        complete = ReplayCompleteness.FULL_REPLAY if status == HistoricalOptionStatus.AVAILABLE else ReplayCompleteness.PARTIAL_OPTION_REPLAY if status == HistoricalOptionStatus.PARTIAL else ReplayCompleteness.CANDLE_ONLY_REPLAY
        flags = tuple(x for x, yes in (("CANDLES_EMPTY", included.empty), ("DUPLICATE_CANDLES_REMOVED", duplicates > 0), ("FUTURE_CANDLES_EXCLUDED", future > 0), ("CANDLES_INSUFFICIENT", len(included) < self.settings.minimum_candles), ("PARTIAL_OPTION_DATA", status == HistoricalOptionStatus.PARTIAL), ("OPTION_DATA_UNAVAILABLE", status == HistoricalOptionStatus.UNAVAILABLE)) if yes)
        metadata = ReplayMetadata(self.mode, analysis.to_pydatetime(), cutoff.to_pydatetime(), None if included.empty else included.iloc[-1]["timestamp"].to_pydatetime(), option[0] if option else None, self.candle_source, "historical_option_snapshot" if option else None, True, True, True, complete, status, future, invalid, duplicates, int((included["timestamp"].dt.date < request.trading_date).sum()) if not included.empty else 0, int((included["timestamp"].dt.date == request.trading_date).sum()) if not included.empty else 0, flags, ("Point-in-time replay; live fallback is prohibited.",))
        option_result = dict(option[1]) if option else {}
        return MarketSnapshot(option_result=option_result, intelligence=dict((current_context or {}).get("intelligence", {})), historical_candles=included, timestamps={"analysis": analysis.isoformat()}, selected_instrument=request.underlying, expiry=str(request.expiry or ""), timeframe=request.interval_minutes, data_quality={"recommendation_available": bool(option_result), "quality_flags": flags}, data_mode=self.mode, analysis_timestamp=analysis.to_pydatetime(), data_cutoff_timestamp=cutoff.to_pydatetime(), replay_metadata=metadata)


class SampleDataProvider(HistoricalReplayProvider):
    mode = DataMode.SAMPLE_DATA
    def __init__(self, settings: ReplaySettings = ReplaySettings()) -> None:
        super().__init__(self._sample, settings=settings, candle_source="deterministic_sample")
    @staticmethod
    def _sample(request: ReplayRequest) -> pd.DataFrame:
        base = normalize_timestamp(datetime.combine(request.trading_date, time(9, 15)))
        direction = -1 if request.sample_scenario in {"BEARISH_EXPANSION", "FALSE_BREAKDOWN", "DISTRIBUTION"} else 1
        rows = [{"timestamp": base + timedelta(minutes=i), "open": 100 + direction*i*.1, "high": 101 + direction*i*.1, "low": 99 + direction*i*.1, "close": 100.5 + direction*i*.1, "volume": 1000+i*10} for i in range(180)]
        if request.sample_scenario == "MALFORMED_CANDLE_DATA": rows.append({"timestamp": "bad", "open": "x"})
        return pd.DataFrame(rows)
    def build_market_snapshot(self, **kwargs: Any) -> MarketSnapshot:
        request = kwargs.get("request"); request.validate(self.settings, sample=True)
        snapshot = super().build_market_snapshot(**kwargs)
        meta = dataclass_replace(snapshot.replay_metadata, mode=self.mode, replay_completeness=ReplayCompleteness.SAMPLE_REPLAY, explanations=("Deterministic sample replay — not for trading.",))
        return dataclass_replace(snapshot, data_mode=self.mode, replay_metadata=meta)


def dataclass_replace(instance: Any, **changes: Any) -> Any:
    from dataclasses import replace
    return replace(instance, **changes)


class LiveUpstoxProvider:
    """Thin adapter preserving the existing Upstox acquisition contract."""
    mode = DataMode.LIVE
    def __init__(self, client: Any) -> None: self.client = client
    def build_market_snapshot(self, *, request: ReplayRequest | None = None, current_context: Mapping[str, object] | None = None) -> MarketSnapshot:
        if request is not None: raise ValueError("LIVE mode does not accept ReplayRequest")
        context = dict(current_context or {})
        metadata = ReplayMetadata(self.mode, None, None, None, None, "upstox_live", "upstox_live", False, False, False, ReplayCompleteness.LIVE, HistoricalOptionStatus.LIVE)
        return MarketSnapshot(option_result=context.get("option_result", {}), intelligence=context.get("intelligence", {}), historical_candles=context.get("historical_candles"), timestamps=context.get("timestamps", {}), selected_instrument=str(context.get("underlying", "")), expiry=str(context.get("expiry", "")), timeframe=context.get("timeframe"), data_quality=context.get("data_quality", {}), data_mode=self.mode, replay_metadata=metadata)


def filter_history_at_cutoff(frame: Any, cutoff: datetime | None) -> Any:
    """Return replay-scoped history; unavailable timestamps yield no history."""
    if cutoff is None or not isinstance(frame, pd.DataFrame): return frame
    if frame.empty: return frame.copy()
    column = next((c for c in ("timestamp", "created_at", "captured_at") if c in frame), None)
    if column is None: return frame.iloc[0:0].copy()
    stamps = pd.to_datetime(frame[column], errors="coerce", utc=True).dt.tz_convert(MARKET_TZ)
    return frame.loc[stamps <= normalize_timestamp(cutoff)].copy().reset_index(drop=True)
