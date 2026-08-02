from datetime import date, datetime, timezone

import pandas as pd
import pytest

from itos_platform.replay import (
    DataMode, HistoricalOptionStatus, HistoricalReplayProvider, ReplayCompleteness,
    ReplayRequest, SampleDataProvider, filter_history_at_cutoff, normalize_candles,
)


def request(**changes):
    values = dict(underlying="NIFTY", instrument_key="NSE_INDEX|Nifty 50",
                  trading_date=date(2026, 7, 30), replay_timestamp=datetime(2026, 7, 30, 10, 17), interval_minutes=5)
    values.update(changes)
    return ReplayRequest(**values)


def candles():
    return pd.DataFrame([{"timestamp": f"2026-07-30 10:{minute:02}:00", "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": None} for minute in (20, 10, 15, 15)])


def test_request_validation_boundaries_and_errors():
    request(replay_timestamp=datetime(2026, 7, 30, 9, 15)).validate()
    request(replay_timestamp=datetime(2026, 7, 30, 15, 30)).validate()
    with pytest.raises(ValueError, match="trading_date"): request(trading_date=date(2026, 7, 29)).validate()
    with pytest.raises(ValueError, match="outside"): request(replay_timestamp=datetime(2026, 7, 30, 9, 14)).validate()
    with pytest.raises(ValueError, match="unsupported"): request(interval_minutes=2).validate()


def test_normalization_is_sorted_deduplicated_and_non_mutating():
    source = candles(); normalized, invalid, duplicate = normalize_candles(source)
    assert duplicate == 1 and invalid == 0 and len(source) == 4
    assert normalized.timestamp.is_monotonic_increasing
    assert pd.isna(normalized.iloc[0].volume)


def test_replay_excludes_incomplete_and_future_candles():
    snapshot = HistoricalReplayProvider(lambda _: candles()).build_market_snapshot(request=request())
    assert snapshot.data_mode is DataMode.HISTORICAL_REPLAY
    assert snapshot.historical_candles.timestamp.dt.minute.tolist() == [10]
    assert snapshot.replay_metadata.future_candle_count_excluded == 2
    assert snapshot.replay_metadata.replay_completeness is ReplayCompleteness.CANDLE_ONLY_REPLAY


def test_future_option_snapshot_is_rejected():
    class Options:
        def nearest_at_or_before(self, **kwargs):
            return datetime(2026, 7, 30, 10, 20), {"chain": "future"}, HistoricalOptionStatus.AVAILABLE
    snapshot = HistoricalReplayProvider(lambda _: candles(), option_source=Options()).build_market_snapshot(request=request())
    assert snapshot.option_result == {}


@pytest.mark.parametrize("scenario", ["BULLISH_EXPANSION", "BEARISH_EXPANSION", "RANGE_COMPRESSION", "FALSE_BREAKOUT", "FALSE_BREAKDOWN"])
def test_sample_scenarios_are_deterministic_and_not_for_trading(scenario):
    req = request(interval_minutes=1, sample_scenario=scenario)
    provider = SampleDataProvider(); first = provider.build_market_snapshot(request=req); second = provider.build_market_snapshot(request=req)
    pd.testing.assert_frame_equal(first.historical_candles, second.historical_candles)
    assert first.replay_metadata == second.replay_metadata
    assert first.replay_metadata.replay_completeness is ReplayCompleteness.SAMPLE_REPLAY
    assert "not for trading" in first.replay_metadata.explanations[0]


def test_history_isolation_excludes_future_and_unknown_timestamp():
    history = pd.DataFrame({"timestamp": ["2026-07-30T04:30:00Z", "2026-07-30T05:30:00Z"], "value": [1, 2]})
    result = filter_history_at_cutoff(history, datetime(2026, 7, 30, 10, 15))
    assert result.value.tolist() == [1]
    assert filter_history_at_cutoff(pd.DataFrame({"value": [1]}), datetime.now()).empty


def test_utc_provider_timestamp_converts_to_india():
    frame = pd.DataFrame({"timestamp": [datetime(2026, 7, 30, 4, 45, tzinfo=timezone.utc)], "open": [1], "high": [2], "low": [0], "close": [1]})
    normalized, _, _ = normalize_candles(frame)
    assert normalized.iloc[0].timestamp.hour == 10 and normalized.iloc[0].timestamp.minute == 15
