"""State and navigation primitives for the Historical Replay workspace.

The module deliberately has no Streamlit dependency.  UI reruns may therefore
render a frozen result without re-running, or accidentally mixing, analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, MutableMapping, Sequence

import pandas as pd

from .replay import DataMode, ReplayCompleteness, ReplayMetadata, ReplayRequest, ReplaySettings, normalize_candles, normalize_timestamp


REPLAY_STATE_DEFAULTS: dict[str, Any] = {
    "replay_data_mode": DataMode.LIVE,
    "replay_selected_workspace": "Analyst Dashboard",
    "replay_current_request": None,
    "replay_current_timestamp": None,
    "replay_current_candle_index": None,
    "replay_candle_timestamps": (),
    "replay_frozen_result": None,
    "replay_history_points": (),
    "replay_outcome_state": None,
    "replay_error": None,
    "replay_last_successful_metadata": None,
    "replay_error_count": 0,
    "replay_requested_timestamp": None,
}


@dataclass(frozen=True)
class ReplayUXSettings:
    default_workspace: str = "Analyst Dashboard"
    available_workspaces: tuple[str, ...] = ("Analyst Dashboard", "Historical Replay")
    default_replay_interval: int = 5
    replay_interval_options: tuple[int, ...] = (1, 3, 5, 10, 15, 30, 60)
    outcome_horizons: tuple[int, ...] = (5, 15, 30)
    replay_timeline_maximum_points: int = 100
    sample_scenarios: tuple[str, ...] = (
        "BULLISH_EXPANSION", "BEARISH_EXPANSION", "RANGE_COMPRESSION",
        "FALSE_BREAKOUT", "FALSE_BREAKDOWN", "ACCUMULATION", "DISTRIBUTION",
        "MISSING_OPTION_DATA", "MALFORMED_CANDLE_DATA",
    )
    replay_banner_enabled: bool = True
    outcome_preview_enabled: bool = True
    replay_controls_enabled: bool = True
    replay_statistics_enabled: bool = True


@dataclass(frozen=True)
class ReplayTimelinePoint:
    replay_timestamp: datetime
    recommendation: str
    institutional_bias: str
    decision_confidence: float
    validation_state: str
    ranking_state: str
    best_ce: str | None
    best_pe: str | None
    major_blocker: str | None
    replay_completeness: ReplayCompleteness


@dataclass(frozen=True)
class ReplayOutcome:
    analysis_timestamp: datetime
    reference_price: float | None
    price_after_5m: float | None = None
    change_after_5m: float | None = None
    price_after_15m: float | None = None
    change_after_15m: float | None = None
    price_after_30m: float | None = None
    change_after_30m: float | None = None
    end_of_session_price: float | None = None
    end_of_session_change: float | None = None
    maximum_favourable_excursion: float | None = None
    maximum_adverse_excursion: float | None = None
    future_data_available: bool = False
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


def initialize_replay_state(state: MutableMapping[str, Any]) -> None:
    for key, value in REPLAY_STATE_DEFAULTS.items():
        state.setdefault(key, value)


def reset_replay_state(state: MutableMapping[str, Any], *, preserve_mode: bool = True) -> None:
    mode = state.get("replay_data_mode", DataMode.LIVE)
    workspace = state.get("replay_selected_workspace", "Analyst Dashboard")
    for key, value in REPLAY_STATE_DEFAULTS.items():
        state[key] = value
    if preserve_mode:
        state["replay_data_mode"], state["replay_selected_workspace"] = mode, workspace


def change_data_mode(state: MutableMapping[str, Any], mode: DataMode) -> None:
    if not isinstance(mode, DataMode):
        raise TypeError("Data mode must use the DataMode contract")
    if state.get("replay_data_mode") is not mode:
        reset_replay_state(state, preserve_mode=False)
        state["replay_data_mode"] = mode
        state["replay_selected_workspace"] = (
            "Analyst Dashboard" if mode is DataMode.LIVE else "Historical Replay"
        )


def completed_candle_timestamps(candles: pd.DataFrame, request: ReplayRequest) -> tuple[datetime, ...]:
    frame, _, _ = normalize_candles(candles)
    if frame.empty:
        return ()
    day = frame[frame.timestamp.dt.date == request.trading_date]
    # A timestamp is a candle open; navigation points are its completion time.
    stamps = day.timestamp + pd.Timedelta(minutes=request.interval_minutes)
    settings = ReplaySettings()
    close = normalize_timestamp(datetime.combine(request.trading_date, settings.market_close))
    return tuple(stamp.to_pydatetime() for stamp in stamps[stamps <= close])


def resolve_cutoff(timestamps: Sequence[datetime], requested: datetime) -> tuple[int, datetime]:
    requested_stamp = normalize_timestamp(requested)
    eligible = []
    for index, stamp in enumerate(timestamps):
        try:
            normalized_stamp = normalize_timestamp(stamp)
        except (TypeError, ValueError):
            continue
        if normalized_stamp <= requested_stamp:
            eligible.append((index, normalized_stamp.to_pydatetime()))
    if not eligible:
        raise ValueError("No completed candle exists at or before the requested replay time")
    return max(eligible, key=lambda item: item[1])


def move_candle(timestamps: Sequence[datetime], current_index: int, step: int) -> tuple[int, datetime]:
    target = current_index + step
    if target < 0 or target >= len(timestamps):
        raise IndexError("No completed candle is available in that direction")
    return target, timestamps[target]


def append_timeline_point(points: Sequence[ReplayTimelinePoint], point: ReplayTimelinePoint,
                          maximum: int = 100) -> tuple[ReplayTimelinePoint, ...]:
    # Re-executing one cutoff deterministically replaces that cutoff, never invents points.
    by_timestamp = {item.replay_timestamp: item for item in points}
    by_timestamp[point.replay_timestamp] = point
    return tuple(sorted(by_timestamp.values(), key=lambda item: item.replay_timestamp))[-maximum:]


def build_outcome(analysis_candles: pd.DataFrame, future_candles: pd.DataFrame,
                  analysis_timestamp: datetime) -> ReplayOutcome:
    """Calculate informational movement from a physically separate future frame."""
    past, _, _ = normalize_candles(analysis_candles)
    reference = None if past.empty else float(past.iloc[-1].close)
    normalized_analysis = normalize_timestamp(analysis_timestamp)

    def unavailable() -> ReplayOutcome:
        return ReplayOutcome(
            analysis_timestamp=normalized_analysis.to_pydatetime(),
            reference_price=reference,
            future_data_available=False,
            quality_flags=("FUTURE_DATA_UNAVAILABLE",),
            explanations=("Outcome data was not used in the replay decision.",),
        )

    if not isinstance(future_candles, pd.DataFrame) or future_candles.empty:
        return unavailable()

    # normalize_candles copies its input, applies the canonical replay timezone,
    # and removes invalid timestamps without touching the analysis snapshot.
    future, _, _ = normalize_candles(future_candles.copy(deep=True))
    if future.empty:
        return unavailable()

    after = future[future.timestamp >= normalized_analysis].copy()
    if after.empty:
        return unavailable()

    def at(minutes: int) -> tuple[float | None, float | None]:
        candidates = after[after.timestamp >= normalized_analysis + timedelta(minutes=minutes)]
        price = None if candidates.empty else float(candidates.iloc[0].close)
        return price, None if price is None or reference is None else price - reference
    p5, c5 = at(5); p15, c15 = at(15); p30, c30 = at(30)
    end = None if after.empty else float(after.iloc[-1].close)
    highs = after.high.astype(float) if not after.empty else pd.Series(dtype=float)
    lows = after.low.astype(float) if not after.empty else pd.Series(dtype=float)
    return ReplayOutcome(
        normalized_analysis.to_pydatetime(), reference, p5, c5, p15, c15, p30, c30, end,
        None if end is None or reference is None else end-reference,
        None if highs.empty or reference is None else float(highs.max()-reference),
        None if lows.empty or reference is None else float(lows.min()-reference),
        True,
        (),
        ("Outcome data was not used in the replay decision.",),
    )


class ReplaySessionController:
    """Runs explicitly requested points and stores immutable UI artifacts."""
    def __init__(self, state: MutableMapping[str, Any], executor: Callable[[ReplayRequest], Any],
                 settings: ReplayUXSettings = ReplayUXSettings()) -> None:
        self.state, self.executor, self.settings = state, executor, settings
        initialize_replay_state(state)

    def run(self, request: ReplayRequest, timeline_factory: Callable[[Any, ReplayMetadata], ReplayTimelinePoint]) -> Any:
        try:
            request.validate(sample=request.sample_scenario is not None)
            result = self.executor(request)
            metadata = result.market_snapshot.replay_metadata
            point = timeline_factory(result, metadata)
            self.state["replay_current_request"] = request
            self.state["replay_current_timestamp"] = metadata.data_cutoff_timestamp
            self.state["replay_frozen_result"] = result
            self.state["replay_last_successful_metadata"] = metadata
            self.state["replay_history_points"] = append_timeline_point(
                self.state["replay_history_points"], point,
                self.settings.replay_timeline_maximum_points,
            )
            self.state["replay_outcome_state"] = None
            self.state["replay_error"] = None
            return result
        except Exception as exc:
            self.state["replay_error"] = safe_replay_error(exc)
            self.state["replay_error_count"] += 1
            raise

    def run_at(self, timestamp: datetime, timeline_factory: Callable[[Any, ReplayMetadata], ReplayTimelinePoint]) -> Any:
        request = self.state.get("replay_current_request")
        if request is None:
            raise ValueError("Run Replay before navigating candles")
        return self.run(replace(request, replay_timestamp=timestamp), timeline_factory)


def safe_replay_error(error: Exception) -> str:
    known = (ValueError, LookupError, RuntimeError)
    return str(error) if isinstance(error, known) and str(error) else "Replay could not be constructed safely."


def replay_statistics(points: Sequence[ReplayTimelinePoint], errors: int = 0) -> dict[str, Any]:
    confidences = [point.decision_confidence for point in points]
    return {
        "points_executed": len(points),
        "eligible_ranking_points": sum(p.ranking_state.lower() == "eligible" for p in points),
        "average_confidence": sum(confidences) / len(confidences) if confidences else None,
        "highest_confidence": max(confidences) if confidences else None,
        "lowest_confidence": min(confidences) if confidences else None,
        "replay_errors": errors,
        "current_completeness": points[-1].replay_completeness.value if points else ReplayCompleteness.UNAVAILABLE.value,
    }
