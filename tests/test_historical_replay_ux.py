"""Behavioural specifications for Sprint 18.4B (no source inspection)."""
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import pytest

from itos_platform.replay import DataMode, ReplayCompleteness, ReplayMetadata, ReplayRequest
from itos_platform.replay_ux import (
    REPLAY_STATE_DEFAULTS, ReplaySessionController, ReplayTimelinePoint,
    append_timeline_point, build_outcome, change_data_mode,
    completed_candle_timestamps, initialize_replay_state, move_candle,
    replay_statistics, reset_replay_state, resolve_cutoff,
)


DAY = date(2026, 7, 30)


def request(stamp=datetime(2026, 7, 30, 10, 0), interval=5, **changes):
    values = dict(underlying="NIFTY", instrument_key="NSE_INDEX|Nifty 50",
                  trading_date=DAY, replay_timestamp=stamp, interval_minutes=interval)
    values.update(changes)
    return ReplayRequest(**values)


def candles():
    return pd.DataFrame([
        {"timestamp": f"2026-07-30 09:{minute:02}", "open": 100+minute, "high": 102+minute,
         "low": 99+minute, "close": 101+minute, "volume": 10}
        for minute in (15, 20, 25, 30, 35, 40, 45, 50, 55)
    ])


def metadata(stamp=datetime(2026, 7, 30, 10, 0)):
    return ReplayMetadata(DataMode.HISTORICAL_REPLAY, stamp, stamp, stamp, None,
                          "fixture", None, True, True, True,
                          ReplayCompleteness.CANDLE_ONLY_REPLAY,
                          __import__("itos_platform.replay", fromlist=["HistoricalOptionStatus"]).HistoricalOptionStatus.UNAVAILABLE)


def point(stamp, confidence=50, ranking="not eligible"):
    return ReplayTimelinePoint(stamp, "WAIT", "Neutral", confidence, "ineligible",
                               ranking, None, None, "fixture", ReplayCompleteness.CANDLE_ONLY_REPLAY)


def test_modes_are_typed_and_mode_change_clears_only_replay_state():
    state = {"option_result": {"live": True}}
    initialize_replay_state(state)
    state["replay_frozen_result"] = object()
    change_data_mode(state, DataMode.HISTORICAL_REPLAY)
    assert state["replay_data_mode"] is DataMode.HISTORICAL_REPLAY
    assert state["replay_selected_workspace"] == "Historical Replay"
    assert state["replay_frozen_result"] is None
    assert state["option_result"] == {"live": True}
    with pytest.raises(TypeError):
        change_data_mode(state, "LIVE")


@pytest.mark.parametrize("stamp", [datetime(2026, 7, 30, 9, 15), datetime(2026, 7, 30, 12), datetime(2026, 7, 30, 15, 30)])
def test_valid_session_boundaries(stamp):
    request(stamp).validate()


@pytest.mark.parametrize("stamp", [datetime(2026, 7, 30, 9, 14), datetime(2026, 7, 30, 15, 31)])
def test_outside_session_is_rejected(stamp):
    with pytest.raises(ValueError, match="outside"):
        request(stamp).validate()


def test_invalid_date_and_interval_are_rejected_without_creating_decision():
    with pytest.raises(ValueError, match="trading_date"):
        request(trading_date=date(2026, 7, 29)).validate()
    with pytest.raises(ValueError, match="unsupported"):
        request(interval=2).validate()


def test_navigation_uses_actual_completed_candles_and_boundaries():
    stamps = completed_candle_timestamps(candles(), request())
    assert stamps[0].time().isoformat() == "09:20:00"
    assert move_candle(stamps, 0, 1) == (1, stamps[1])
    assert move_candle(stamps, 1, -1) == (0, stamps[0])
    with pytest.raises(IndexError): move_candle(stamps, 0, -1)
    with pytest.raises(IndexError): move_candle(stamps, len(stamps)-1, 1)


def test_jump_resolves_nearest_prior_completed_candle():
    stamps = completed_candle_timestamps(candles(), request())
    index, resolved = resolve_cutoff(stamps, datetime(2026, 7, 30, 9, 33))
    assert resolved.time().isoformat() == "09:30:00" and index == 2
    with pytest.raises(ValueError, match="No completed"):
        resolve_cutoff(stamps, datetime(2026, 7, 30, 9, 16))


def test_reset_clears_replay_outputs_but_not_live_keys():
    state = {"live_history": [1], "replay_data_mode": DataMode.SAMPLE_DATA,
             "replay_frozen_result": object(), "replay_history_points": (point(datetime.now()),)}
    reset_replay_state(state)
    assert state["live_history"] == [1]
    assert state["replay_frozen_result"] is None and state["replay_history_points"] == ()
    assert all(key.startswith("replay_") for key in REPLAY_STATE_DEFAULTS)


def test_timeline_contains_only_executed_points_is_sorted_and_deduplicated():
    later = point(datetime(2026, 7, 30, 10), 70)
    earlier = point(datetime(2026, 7, 30, 9, 30), 50)
    replacement = point(datetime(2026, 7, 30, 10), 71)
    values = append_timeline_point((later,), earlier)
    values = append_timeline_point(values, replacement)
    assert values == (earlier, replacement)


def test_outcome_horizons_are_separate_and_do_not_mutate_analysis():
    analysis = candles().iloc[:4].copy(deep=True)
    frozen = analysis.copy(deep=True)
    future = pd.DataFrame([
        {"timestamp": "2026-07-30 09:35", "open": 130, "high": 132, "low": 129, "close": 131},
        {"timestamp": "2026-07-30 09:45", "open": 140, "high": 142, "low": 138, "close": 141},
        {"timestamp": "2026-07-30 10:00", "open": 150, "high": 154, "low": 147, "close": 151},
    ])
    outcome = build_outcome(analysis, future, datetime(2026, 7, 30, 9, 30))
    assert outcome.price_after_5m == 131 and outcome.price_after_15m == 141 and outcome.price_after_30m == 151
    assert outcome.end_of_session_price == 151 and outcome.future_data_available
    pd.testing.assert_frame_equal(analysis, frozen)


def test_unavailable_outcome_horizon_degrades_safely():
    outcome = build_outcome(candles(), candles().iloc[0:0], datetime(2026, 7, 30, 10))
    assert not outcome.future_data_available
    assert outcome.price_after_5m is None and "FUTURE_DATA_UNAVAILABLE" in outcome.quality_flags


def test_statistics_are_session_local_and_do_not_claim_performance():
    stats = replay_statistics((point(datetime(2026, 7, 30, 9, 30), 40, "eligible"),
                               point(datetime(2026, 7, 30, 9, 45), 80)), errors=2)
    assert stats["points_executed"] == 2 and stats["eligible_ranking_points"] == 1
    assert stats["average_confidence"] == 60 and stats["replay_errors"] == 2
    assert "win_rate" not in stats


def test_controller_freezes_once_and_outcome_reveal_cannot_change_it():
    @dataclass(frozen=True)
    class Snapshot: replay_metadata: ReplayMetadata
    @dataclass(frozen=True)
    class Result: market_snapshot: Snapshot
    calls = []
    state = {}
    controller = ReplaySessionController(state, lambda req: calls.append(req) or Result(Snapshot(metadata(req.replay_timestamp))))
    result = controller.run(request(), lambda _result, meta: point(meta.analysis_timestamp))
    frozen = state["replay_frozen_result"]
    state["replay_outcome_state"] = build_outcome(candles(), candles(), datetime(2026, 7, 30, 10))
    assert len(calls) == 1 and result is frozen and state["replay_frozen_result"] is frozen


def test_controller_never_falls_back_when_provider_fails():
    state = {"live_result": object()}
    controller = ReplaySessionController(state, lambda _request: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    with pytest.raises(RuntimeError):
        controller.run(request(), lambda *_: point(datetime.now()))
    assert state["replay_frozen_result"] is None and state["live_result"] is not None
    assert state["replay_error"] == "provider unavailable"
