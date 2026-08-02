"""Deterministic behavioral coverage for Sprint 18.4D.1 (no network calls)."""
from dataclasses import asdict, replace
from datetime import date, datetime

import pandas as pd
import pytest

from itos_platform.historical_sync import (
    DEFAULT_HISTORICAL_INSTRUMENTS, HistoricalAuthenticationError,
    HistoricalInstrument, HistoricalMalformedResponseError, HistoricalSyncManager,
    HistoricalSyncSettings, UpstoxHistoricalSyncProvider, build_date_chunks,
    expected_weekdays, invalidate_historical_analytics_cache,
    normalize_historical_candles, resolve_historical_instrument,
)
from itos_platform.market_lake import (
    HistoricalRangeRequest, LocalHistoricalMarketLake, MarketLakeSettings, PeriodPreset,
    resolve_period,
)


class FakeClient:
    def __init__(self, frame=None, error=None, token="TOP-SECRET"):
        self.frame = frame if frame is not None else pd.DataFrame()
        self.error = error; self.access_token = token; self.calls = []

    def get_historical_candles(self, instrument_key, from_date, to_date, interval, unit):
        self.calls.append((instrument_key, from_date, to_date, interval, unit))
        if self.error: raise self.error
        return self.frame.copy(deep=True)


def candles(*days):
    return pd.DataFrame([{"timestamp": f"{day}T09:15:00+05:30", "open": 100, "high": 102,
        "low": 99, "close": 101, "volume": None, "oi": None} for day in days])


def manager(tmp_path, client):
    lake = LocalHistoricalMarketLake(MarketLakeSettings(market_lake_root=tmp_path))
    return HistoricalSyncManager(provider=UpstoxHistoricalSyncProvider(client=client),
        market_lake=lake, settings=replace(HistoricalSyncSettings(), historical_sync_retry_delay_seconds=0,
        historical_sync_rate_limit_backoff_seconds=0), sleeper=lambda _: None)


def test_injected_authenticated_client_is_reused_without_secondary_login(tmp_path):
    client = FakeClient(candles("2026-07-31")); service = manager(tmp_path, client)
    request = HistoricalRangeRequest("NIFTY", "NSE_INDEX|Nifty 50", date(2026, 7, 31), date(2026, 7, 31), include_options=False)
    result = service.sync_missing_raw(request)
    assert result.completed_dates == (date(2026, 7, 31),)
    assert client.calls and service.provider._client is client


def test_missing_and_invalid_authentication_are_sanitized():
    with pytest.raises(HistoricalAuthenticationError, match="^Historical Upstox authentication failed\\.$"):
        UpstoxHistoricalSyncProvider(client=None)
    class AuthenticationFailure(Exception): pass
    provider = UpstoxHistoricalSyncProvider(client=FakeClient(error=AuthenticationFailure("TOP-SECRET")))
    with pytest.raises(HistoricalAuthenticationError, match="^Historical Upstox authentication failed\\.$") as captured:
        provider.fetch_historical_candles(instrument_key="key", start_date=date(2026,1,1), end_date=date(2026,1,1), interval_minutes=1)
    assert "TOP-SECRET" not in str(captured.value)


def test_runtime_provider_and_token_are_not_in_plan_or_manifest(tmp_path):
    service = manager(tmp_path, FakeClient(token="TOP-SECRET"))
    request = HistoricalRangeRequest("NIFTY", "NSE_INDEX|Nifty 50", date(2026,7,27), date(2026,7,31), include_options=False)
    plan = service.preview_plan(request)
    assert "TOP-SECRET" not in repr(plan)
    assert "client" not in asdict(plan)
    service._checkpoint(request)
    assert "TOP-SECRET" not in (tmp_path / "manifest/upstox/NSE_INDEX_Nifty_50/1/dataset_manifest.json").read_text()


def test_instrument_resolution_and_override():
    assert resolve_historical_instrument("nifty").instrument_key == "NSE_INDEX|Nifty 50"
    assert resolve_historical_instrument("BANKNIFTY").instrument_key == "NSE_INDEX|Nifty Bank"
    custom = {**DEFAULT_HISTORICAL_INSTRUMENTS, "NIFTY": HistoricalInstrument("NIFTY", "override")}
    assert resolve_historical_instrument("NIFTY", custom).instrument_key == "override"
    with pytest.raises(ValueError): resolve_historical_instrument("FINNIFTY")


@pytest.mark.parametrize("preset,days", [(PeriodPreset.WEEK,7), (PeriodPreset.MONTH,30),
    (PeriodPreset.THREE_MONTHS,90), (PeriodPreset.SIX_MONTHS,180), (PeriodPreset.ONE_YEAR,365)])
def test_supported_period_resolution(preset, days):
    start, end = resolve_period(preset, date(2026,7,31))
    assert (end-start).days + 1 == days


def test_custom_period_and_expected_sessions():
    start, end = resolve_period(PeriodPreset.CUSTOM, date(2026,7,31), custom_start=date(2026,7,27))
    assert expected_weekdays(start, end) == tuple(date(2026,7,d) for d in range(27,32))


def test_plan_selects_missing_skips_complete_and_estimates_points(tmp_path):
    service = manager(tmp_path, FakeClient()); request = HistoricalRangeRequest("NIFTY", "key", date(2026,7,27), date(2026,7,31), include_options=False)
    service._checkpoint(request, completed=(date(2026,7,27),))
    plan = service.preview_plan(request, cadence_minutes=5)
    assert plan.complete_dates == (date(2026,7,27),)
    assert date(2026,7,27) not in plan.dates_to_download
    assert len(plan.missing_dates) == 4 and plan.estimated_analysis_points == 375


def test_chunking_is_bounded_unique_and_has_correct_boundaries():
    days = tuple(date(2026,1,1) + pd.Timedelta(days=i) for i in range(70))
    chunks = build_date_chunks(days, 30)
    flattened = tuple(day for chunk in chunks for day in chunk.requested_dates)
    assert len(chunks) == 3 and len(flattened) == len(set(flattened))
    assert all((chunk.end_date-chunk.start_date).days < 30 for chunk in chunks)


def test_normalization_timezone_sort_duplicate_invalid_and_missing_values():
    frame = pd.DataFrame([
        {"timestamp":"2026-07-31T09:16:00+05:30","open":2,"high":3,"low":1,"close":2,"volume":None},
        {"timestamp":"2026-07-31T09:15:00+05:30","open":2,"high":1,"low":3,"close":2},
        {"timestamp":"2026-07-31T09:16:00+05:30","open":4,"high":5,"low":3,"close":4},])
    result = normalize_historical_candles(frame)
    assert len(result) == 1 and str(result.timestamp.dt.tz) == "Asia/Kolkata"
    assert pd.isna(result.iloc[0].volume) and pd.isna(result.iloc[0].open_interest)
    assert result.iloc[0].open == 4


def test_malformed_response_rejected_without_recommendation():
    with pytest.raises(HistoricalMalformedResponseError): normalize_historical_candles(pd.DataFrame({"price":[1]}))


def test_partition_checkpoint_resume_retry_and_rebuild(tmp_path):
    client = FakeClient(candles("2026-07-30", "2026-07-31")); service = manager(tmp_path, client)
    request = HistoricalRangeRequest("NIFTY", "key", date(2026,7,30), date(2026,7,31), include_options=False)
    first = service.sync_missing_raw(request); second = service.sync_missing_raw(request)
    rebuilt = service.sync_missing_raw(replace(request, rebuild_raw=True))
    assert len(first.completed_dates) == 2 and len(second.skipped_dates) == 2
    assert len(rebuilt.completed_dates) == 2 and len(client.calls) == 2


def test_empty_response_is_no_data_not_complete(tmp_path):
    service = manager(tmp_path, FakeClient(pd.DataFrame(columns=["timestamp","open","high","low","close"])))
    request = HistoricalRangeRequest("NIFTY", "key", date(2026,7,31), date(2026,7,31), include_options=False)
    result = service.sync_missing_raw(request)
    assert result.no_data_dates == (date(2026,7,31),) and not result.completed_dates


def test_cancellation_preserves_previous_checkpoint(tmp_path):
    service = manager(tmp_path, FakeClient(candles("2026-07-30", "2026-07-31")))
    request = HistoricalRangeRequest("NIFTY", "key", date(2026,7,30), date(2026,7,31), include_options=False)
    checks = iter((False, False, True, True))
    result = service.sync_missing_raw(request, cancel=lambda: next(checks, True))
    assert result.cancelled


def test_cache_invalidation_is_namespace_limited():
    state = {"historical_analytics_result": 1, "historical_analytics_filters": 2,
        "live_result": 3, "replay_result": 4}
    invalidate_historical_analytics_cache(state)
    assert "historical_analytics_result" not in state
    assert state["historical_analytics_filters"] == 2 and state["live_result"] == 3 and state["replay_result"] == 4
