"""Streamlit presentation adapter for the additive replay workspace."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
from typing import Any, Callable, MutableMapping

import pandas as pd
import streamlit as st

from itos_platform.replay import DataMode, ReplayRequest, ReplaySettings, SAMPLE_SCENARIOS
from itos_platform.replay_ux import (
    ReplayUXSettings, build_outcome, completed_candle_timestamps,
    initialize_replay_state, move_candle, reset_replay_state, resolve_cutoff,
)


def _show_metadata(metadata: Any) -> None:
    st.warning(
        f"**{metadata.mode.value.replace('_', ' ')} MODE**  \n"
        f"Analysis timestamp: {metadata.analysis_timestamp}  \n"
        f"Latest completed candle: {metadata.latest_candle_timestamp or 'Unavailable'}  \n"
        f"Future data excluded: {'Yes' if metadata.look_ahead_protected else 'No'}  \n"
        f"Replay completeness: **{metadata.replay_completeness.value}**  \n"
        f"Option snapshot: **{metadata.historical_option_status.value.title()}**"
    )
    with st.expander("Replay completeness and quality diagnostics"):
        labels = {
            "candle_source": "Candle source", "option_source": "Option source",
            "look_ahead_protected": "Look-ahead protected",
            "candles_cutoff_applied": "Candle cutoff applied",
            "option_cutoff_applied": "Option cutoff applied",
            "option_snapshot_timestamp": "Option snapshot timestamp",
            "future_candle_count_excluded": "Future candles excluded",
            "invalid_row_count": "Invalid rows removed",
            "duplicate_row_count": "Duplicate rows removed",
            "warm_up_candle_count": "Warm-up candle count",
            "replay_session_candle_count": "Replay-session candle count",
            "quality_flags": "Quality flags", "explanations": "Explanations",
        }
        values = asdict(metadata)
        st.dataframe(pd.DataFrame([{"Diagnostic": label, "Value": values[key]} for key, label in labels.items()]),
                     hide_index=True, use_container_width=True)


def render_replay_workspace(mode: DataMode, state: MutableMapping[str, Any],
                            provider_factory: Callable[[DataMode], Any],
                            underlyings: dict[str, str]) -> None:
    """Render replay controls without altering any legacy live widget or state key."""
    initialize_replay_state(state)
    ux = ReplayUXSettings(); replay = ReplaySettings()
    st.header("Historical Replay")
    if mode is DataMode.SAMPLE_DATA:
        st.error("**SAMPLE DATA MODE — NOT FOR TRADING**  \nDeterministic development fixture")

    c1, c2, c3 = st.columns(3)
    underlying = c1.selectbox("Underlying", tuple(underlyings), key="replay_control_underlying")
    instrument = c2.text_input("Instrument key", underlyings[underlying], key="replay_control_instrument")
    interval = c3.selectbox("Candle interval", ux.replay_interval_options,
                            index=ux.replay_interval_options.index(ux.default_replay_interval),
                            key="replay_control_interval")
    c4, c5, c6 = st.columns(3)
    trading_date = c4.date_input("Trading date", value=date.today(), key="replay_control_date")
    replay_time = c5.time_input("Replay time", value=time(10, 15), step=60, key="replay_control_time")
    expiry_text = c6.text_input("Expiry (optional, YYYY-MM-DD)", key="replay_control_expiry")
    scenario = None
    if mode is DataMode.SAMPLE_DATA:
        scenario = st.selectbox("Sample scenario", ux.sample_scenarios, key="replay_control_scenario")
    request_options = st.columns(2)
    option_requested = request_options[0].checkbox("Historical option snapshot requested", value=True)
    request_options[1].caption(f"Warm-up configured: {replay.warm_up_sessions} prior session(s)")

    try:
        expiry = date.fromisoformat(expiry_text) if expiry_text else None
    except ValueError:
        expiry = None
        st.error("Expiry must use YYYY-MM-DD format.")
    requested = datetime.combine(trading_date, replay_time)

    run, previous, next_, jump, reset = st.columns(5)
    run_clicked = run.button("Run Replay", type="primary", use_container_width=True)
    stamps = state.get("replay_candle_timestamps", ())
    index = state.get("replay_current_candle_index")
    previous_clicked = previous.button("Previous Candle", disabled=index in (None, 0), use_container_width=True)
    next_clicked = next_.button("Next Candle", disabled=index is None or index >= len(stamps)-1, use_container_width=True)
    jump_clicked = jump.button("Jump to Time", disabled=not stamps, use_container_width=True)
    if reset.button("Reset Replay", use_container_width=True):
        reset_replay_state(state)
        st.rerun()

    try:
        provider = provider_factory(mode)
        target = requested
        if previous_clicked:
            index, target = move_candle(stamps, index, -1)
        elif next_clicked:
            index, target = move_candle(stamps, index, 1)
        elif jump_clicked:
            index, target = resolve_cutoff(stamps, requested)
        if run_clicked or previous_clicked or next_clicked or jump_clicked:
            request = ReplayRequest(underlying, instrument, trading_date, target, interval,
                                    expiry, option_requested, scenario)
            request.validate(replay, sample=mode is DataMode.SAMPLE_DATA)
            snapshot = provider.build_market_snapshot(request=request)
            raw = provider.loader(request)
            stamps = completed_candle_timestamps(raw, request)
            index, resolved = resolve_cutoff(stamps, target)
            if resolved != target:
                request = ReplayRequest(underlying, instrument, trading_date, resolved, interval,
                                        expiry, option_requested, scenario)
                snapshot = provider.build_market_snapshot(request=request)
            state.update({
                "replay_current_request": request, "replay_current_timestamp": resolved,
                "replay_current_candle_index": index, "replay_candle_timestamps": stamps,
                "replay_frozen_result": snapshot, "replay_last_successful_metadata": snapshot.replay_metadata,
                "replay_outcome_state": None, "replay_error": None,
                "replay_requested_timestamp": requested,
            })
    except Exception as exc:
        state["replay_error"] = str(exc) or "Replay could not be constructed safely."
        state["replay_error_count"] = state.get("replay_error_count", 0) + 1

    if state.get("replay_error"):
        st.error(state["replay_error"])
    snapshot = state.get("replay_frozen_result")
    if snapshot is None:
        st.info("Configure a replay point and select **Run Replay**. Live data is never used as fallback.")
        return
    st.caption(f"Requested replay time: {state['replay_requested_timestamp']} | Resolved analysis cutoff: {state['replay_current_timestamp']}")
    _show_metadata(snapshot.replay_metadata)
    st.subheader("Frozen replay snapshot")
    st.caption("The existing analytical pipeline consumes this cutoff-filtered snapshot; rendering does not mutate it.")
    st.dataframe(snapshot.historical_candles.tail(20), use_container_width=True, hide_index=True)
    st.subheader("Decision timeline")
    st.info("Decision points appear here only after the existing analytical pipeline successfully executes them.")
    if ux.outcome_preview_enabled and st.button("Reveal Outcome Preview"):
        request = state["replay_current_request"]
        raw = provider_factory(mode).loader(request)
        future = raw[pd.to_datetime(raw["timestamp"], errors="coerce") >= pd.Timestamp(request.replay_timestamp)]
        state["replay_outcome_state"] = build_outcome(snapshot.historical_candles, future, request.replay_timestamp)
    outcome = state.get("replay_outcome_state")
    if outcome:
        st.warning("**OUTCOME DATA** — Not used in the replay decision.")
        st.dataframe(pd.DataFrame([
            {"Horizon": "5 minutes", "Price": outcome.price_after_5m, "Point change": outcome.change_after_5m},
            {"Horizon": "15 minutes", "Price": outcome.price_after_15m, "Point change": outcome.change_after_15m},
            {"Horizon": "30 minutes", "Price": outcome.price_after_30m, "Point change": outcome.change_after_30m},
            {"Horizon": "End of session", "Price": outcome.end_of_session_price, "Point change": outcome.end_of_session_change},
        ]), hide_index=True, use_container_width=True)
