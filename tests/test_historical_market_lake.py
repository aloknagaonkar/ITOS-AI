"""Behavioural coverage for Sprint 18.4C (no source/AST inspection)."""
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from itos_platform.market_lake import (
    DatasetManifest, HistoricalEnrichmentService, HistoricalIngestionService,
    HistoricalIntelligenceRecord, HistoricalOutcomeService, HistoricalRangeRequest,
    IntelligenceQuery, LocalHistoricalMarketLake, MarketLakeSettings, PeriodPreset,
    availability, new_manifest, resolve_period,
)


TODAY = date(2025, 1, 10)


def settings(tmp_path):
    return MarketLakeSettings(market_lake_root=tmp_path, maximum_sync_range=400)


def request(**changes):
    values = dict(underlying="NIFTY", instrument_key="NSE|NIFTY", start_date=TODAY,
                  end_date=TODAY, interval_minutes=1)
    values.update(changes)
    return HistoricalRangeRequest(**values)


def candles(day=TODAY, count=40):
    stamps = pd.date_range(f"{day} 09:15", periods=count, freq="min", tz="Asia/Kolkata")
    return pd.DataFrame({"timestamp": stamps, "open": range(100, 100+count),
        "high": range(101, 101+count), "low": range(99, 99+count),
        "close": range(100, 100+count), "volume": [None] * count})


def intelligence(stamp=None, **changes):
    stamp = stamp or datetime.fromisoformat("2025-01-10T09:20:00+05:30")
    values = dict(provider="archive", instrument_key="NSE|NIFTY", underlying="NIFTY",
        interval_minutes=1, trading_date=TODAY, analysis_timestamp=stamp,
        data_cutoff_timestamp=stamp, latest_completed_candle_timestamp=stamp,
        engine_version="itos-18.4c-v1", schema_version="intelligence-v1",
        replay_completeness="CANDLE_ONLY_REPLAY", recommendation="WAIT",
        compression_state="COMPRESSED", positioning_state="NEUTRAL",
        manipulation_state="NONE", decision_confidence=42.0, values={"top_5_ce": []})
    values.update(changes)
    return HistoricalIntelligenceRecord(**values)


def test_range_validation_and_period_resolution(tmp_path):
    request().validate(settings(tmp_path), today=TODAY)
    with pytest.raises(ValueError): request(start_date=TODAY, end_date=TODAY-timedelta(days=1)).validate(settings(tmp_path), today=TODAY)
    with pytest.raises(ValueError): request(end_date=TODAY+timedelta(days=1)).validate(settings(tmp_path), today=TODAY)
    with pytest.raises(ValueError): request(interval_minutes=2).validate(settings(tmp_path), today=TODAY)
    lengths = {PeriodPreset.WEEK: 7, PeriodPreset.MONTH: 30, PeriodPreset.THREE_MONTHS: 90,
               PeriodPreset.SIX_MONTHS: 180, PeriodPreset.ONE_YEAR: 365}
    for preset, length in lengths.items():
        start, end = resolve_period(preset, TODAY); assert (end-start).days + 1 == length
    assert resolve_period(PeriodPreset.CUSTOM, TODAY, custom_start=TODAY-timedelta(days=2))[0] == TODAY-timedelta(days=2)


def test_partitioned_storage_copies_options_upsert_and_corruption(tmp_path):
    lake = LocalHistoricalMarketLake(settings(tmp_path)); frame = candles()
    lake.store_raw_candles("archive", "NSE|NIFTY", 1, TODAY, frame)
    loaded = lake.load_raw_candles("archive", "NSE|NIFTY", 1, TODAY); loaded.loc[0, "close"] = -1
    assert lake.load_raw_candles("archive", "NSE|NIFTY", 1, TODAY).loc[0, "close"] == 100
    expiry = date(2025, 1, 30); stamp = datetime.fromisoformat("2025-01-10T09:20:00+05:30")
    lake.store_option_snapshots("archive", "NSE|NIFTY", expiry, TODAY, stamp, [{"strike": 22000, "iv": None}])
    assert lake.load_option_snapshots("archive", "NSE|NIFTY", expiry, TODAY)[0]["iv"] is None
    record = intelligence(); lake.store_intelligence_records([record, record])
    query = IntelligenceQuery("NSE|NIFTY", TODAY, TODAY, 1, recommendation="WAIT", compression_state="COMPRESSED")
    assert len(lake.query_intelligence(query)) == 1
    raw_path = lake._raw_path("archive", "NSE|NIFTY", 1, TODAY); raw_path.write_text("corrupt")
    assert lake.load_raw_candles("archive", "NSE|NIFTY", 1, TODAY) is None


def test_manifest_atomic_incremental_retry_no_data_and_secret_redaction(tmp_path):
    lake = LocalHistoricalMarketLake(settings(tmp_path)); req = request()
    calls = []
    def fetch(_request, day):
        calls.append(day)
        if len(calls) == 1: raise RuntimeError("Bearer secret-token")
        return candles(day)
    service = HistoricalIngestionService(lake, fetch, provider="archive")
    first = service.synchronize(req, [TODAY]); assert first.failed_dates == (TODAY,)
    second = service.synchronize(req, [TODAY]); assert second.completed_dates == (TODAY,)
    third = service.synchronize(req, [TODAY]); assert third.skipped_dates == (TODAY,)
    manifest = lake.get_manifest("archive", "NSE|NIFTY", 1)
    assert manifest.available_dates == (TODAY,) and manifest.raw_record_count == 40
    assert "token" not in lake._manifest_path("archive", "NSE|NIFTY", 1).read_text().lower()
    empty_req = request(instrument_key="NSE|EMPTY")
    empty = HistoricalIngestionService(lake, lambda _r, _d: pd.DataFrame(), provider="archive").synchronize(empty_req, [TODAY])
    assert empty.no_data_dates == (TODAY,)


def test_point_enrichment_is_idempotent_and_rejects_lookahead(tmp_path):
    lake = LocalHistoricalMarketLake(settings(tmp_path)); req = request()
    lake.store_raw_candles("archive", req.instrument_key, 1, TODAY, candles(count=7))
    calls = []
    def runner(replay):
        calls.append(replay)
        return {"recommendation": {"side": "WAIT"}, "replay_metadata": type("M", (), {
            "data_cutoff_timestamp": replay.replay_timestamp,
            "latest_candle_timestamp": replay.replay_timestamp,
            "replay_completeness": "CANDLE_ONLY_REPLAY", "quality_flags": ()})()}
    service = HistoricalEnrichmentService(lake, runner, provider="archive")
    assert service.enrich(req, [TODAY], cadence_minutes=3).completed_dates == (TODAY,)
    count = len(lake.query_intelligence(IntelligenceQuery(req.instrument_key, TODAY, TODAY, 1)))
    service.enrich(req, [TODAY], cadence_minutes=3)
    assert len(lake.query_intelligence(IntelligenceQuery(req.instrument_key, TODAY, TODAY, 1))) == count == 3
    assert all(call.replay_timestamp.date() == TODAY for call in calls)


def test_outcomes_remain_separate_and_query_filters(tmp_path):
    lake = LocalHistoricalMarketLake(settings(tmp_path)); record = intelligence()
    lake.store_raw_candles("archive", record.instrument_key, 1, TODAY, candles())
    lake.store_intelligence_records([record])
    outcome = HistoricalOutcomeService(lake, provider="archive").build([record])[0]
    prices = dict(outcome.horizon_prices)
    assert prices[5] == 110 and prices[15] == 120 and prices[30] == 135
    assert outcome.maximum_favourable_excursion == 20
    assert lake.query_intelligence(IntelligenceQuery(record.instrument_key, TODAY, TODAY, minimum_confidence=40,
        positioning_state="NEUTRAL", manipulation_state="NONE", engine_version=record.engine_version)) == (record,)
    assert len(lake.query_outcomes(record.instrument_key, TODAY, TODAY, record.engine_version)) == 1
    assert "horizon_prices" not in lake.query_intelligence(IntelligenceQuery(record.instrument_key, TODAY, TODAY))[0].values


def test_availability_clamps_and_reports_missing():
    req = request(); manifest = new_manifest(req, "archive", MarketLakeSettings())
    manifest = DatasetManifest(**{**manifest.__dict__, "start_date": TODAY, "end_date": TODAY,
        "available_dates": (TODAY,), "intelligence_dates": (), "outcome_dates": (), "option_dates": ()})
    result = availability(manifest, [TODAY])
    assert result.raw_complete_sessions == 1 and result.completeness_percent == pytest.approx(100/3)
    assert result.missing_intelligence_dates == (TODAY,) and result.missing_outcome_dates == (TODAY,)
