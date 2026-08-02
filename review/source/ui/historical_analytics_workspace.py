"""Streamlit presentation for the isolated Historical Analytics workspace."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, timedelta
from typing import Any, Callable, Mapping

import pandas as pd
import streamlit as st

from itos_platform.historical_analytics import (
    HistoricalAnalyticsRequest, HistoricalAnalyticsResult, HistoricalAnalyticsService,
    resolve_analytics_period,
)
from itos_platform.market_lake import (
    HistoricalRangeRequest, LocalHistoricalMarketLake, MarketLakeDeveloperService, PeriodPreset,
)
from itos_platform.historical_sync import (
    HistoricalAuthenticationError, HistoricalSyncManager,
    HistoricalSyncProgress, invalidate_historical_analytics_cache,
)

PREFIX = "historical_analytics_"


@dataclass(frozen=True)
class MarketLakeActions:
    """Existing orchestration callbacks supplied by deployment, never recreated here."""
    sync_missing_data: Callable[[HistoricalRangeRequest], object] | None = None
    build_intelligence: Callable[[HistoricalRangeRequest], object] | None = None
    build_outcomes: Callable[[HistoricalRangeRequest], object] | None = None


def _option(label: str) -> str | None:
    value = st.text_input(label, key=PREFIX+label.lower().replace(" ", "_"))
    return value.strip() or None


def _coverage(result: HistoricalAnalyticsResult) -> None:
    st.subheader("Data Freshness & Coverage")
    request = result.request
    st.caption(f"Selected date range: {request.start_date} → {request.end_date}")
    metrics = (("Expected trading sessions", result.expected_session_count), ("Raw sessions", result.raw_session_count),
        ("Intelligence sessions", result.intelligence_session_count), ("Outcome sessions", result.outcome_session_count),
        ("Option-data sessions", result.option_session_count), ("Data completeness", f"{result.data_completeness:.2f}%"),
        ("Intelligence completeness", f"{result.intelligence_completeness:.2f}%"),
        ("Outcome completeness", f"{result.outcome_completeness:.2f}%"), ("Option completeness", f"{result.option_completeness:.2f}%"),
        ("Engine version", ", ".join(result.engine_versions)), ("Schema version", ", ".join(result.schema_versions)))
    columns = st.columns(4)
    for index, (label, value) in enumerate(metrics): columns[index % 4].metric(label, value)
    st.write("Available dates", result.available_dates or "None")
    st.write("Missing dates", result.missing_dates or "None")
    if result.missing_dates:
        st.warning("Historical data is incomplete for this period.")
        if st.button("Open Developer → Market Lake", key=PREFIX+"open_developer"):
            st.session_state[PREFIX+"developer_open"] = True


def _sections(result: HistoricalAnalyticsResult) -> tuple[tuple[str, Mapping[str, object]], ...]:
    confidence = {"average": result.average_confidence, "median": result.median_confidence,
        "maximum": result.maximum_confidence, "minimum": result.minimum_confidence,
        "above_90": result.confidence_above_90, "above_80": result.confidence_above_80,
        "above_70": result.confidence_above_70, "below_60": result.confidence_below_60}
    outcomes = {"average_5m_movement": result.average_5m_change, "average_15m_movement": result.average_15m_change,
        "average_30m_movement": result.average_30m_change, "average_end_of_session_movement": result.average_eod_change,
        "average_mfe": result.average_mfe, "average_mae": result.average_mae,
        "future_data_coverage": result.future_data_coverage}
    return (("Market Structure", result.market_structure), ("Price & Volume", result.price_volume),
        ("Positioning", result.positioning), ("Compression", result.compression),
        ("Manipulation", result.manipulation), ("Institutional Evidence", result.institutional_evidence),
        ("Decision Confidence", confidence), ("Validation", result.validation),
        ("Trade Opportunity Ranking", result.ranking),
        ("Top 5 CE", {"occurrences": result.top_ce_occurrences}),
        ("Top 5 PE", {"occurrences": result.top_pe_occurrences}), ("Historical Outcomes", outcomes))


def _progress_values(progress: object) -> Mapping[str, Any]:
    """Return plain progress values without asking Streamlit to inspect an object."""
    if is_dataclass(progress) and not isinstance(progress, type):
        return asdict(progress)
    model_dump = getattr(progress, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, Mapping) else {}
    if isinstance(progress, Mapping):
        return progress
    return {
        name: getattr(progress, name, None)
        for name in (
            "completed", "skipped", "failed", "downloaded_rows", "stored_rows",
            "current_date", "chunk_number", "chunk_count", "quality_flags",
            "explanations",
        )
    }


def render_sync_progress(progress: object) -> None:
    """Render sync progress through explicit fields, never object introspection."""
    if isinstance(progress, pd.DataFrame):
        st.dataframe(progress, hide_index=True, use_container_width=True)
        return
    values = _progress_values(progress)

    def integer(name: str) -> int:
        value = values.get(name, 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    completed = integer("completed")
    skipped = integer("skipped")
    failed = integer("failed")
    chunk_number = integer("chunk_number")
    chunk_count = integer("chunk_count")
    processed = completed + skipped + failed
    percent = (100.0 * chunk_number / chunk_count) if chunk_count else (100.0 if processed else 0.0)
    metrics = st.columns(4)
    for column, (label, value) in zip(metrics, (
        ("Completed", completed), ("Skipped", skipped), ("Failed", failed),
        ("Percent complete", f"{min(100.0, max(0.0, percent)):.1f}%"),
    )):
        column.metric(label, value)
    row = st.columns(4)
    row[0].metric("Downloaded rows", integer("downloaded_rows"))
    row[1].metric("Stored rows", integer("stored_rows"))
    row[2].metric("Current date", str(values.get("current_date") or "—"))
    row[3].metric("Current chunk", f"{chunk_number}/{chunk_count}" if chunk_count else "—")
    st.json({
        "quality_flags": list(values.get("quality_flags") or ()),
        "explanations": list(values.get("explanations") or ()),
    })


def _render_sync_result(result: object) -> None:
    """Render a stored result without passing a runtime object to Streamlit."""
    if isinstance(result, pd.DataFrame):
        st.dataframe(result, hide_index=True, use_container_width=True)
    elif is_dataclass(result) and not isinstance(result, type):
        st.json(asdict(result))
    elif isinstance(result, Mapping):
        st.json(dict(result))
    else:
        model_dump = getattr(result, "model_dump", None)
        st.json(model_dump() if callable(model_dump) else {"status": "Unavailable"})


def _developer_panel(lake: LocalHistoricalMarketLake, provider: str, request: HistoricalRangeRequest,
                     actions: MarketLakeActions, manager: HistoricalSyncManager | None,
                     cadence: int) -> None:
    expanded = bool(st.session_state.get(PREFIX+"developer_open", False))
    with st.expander("Developer → Market Lake / Historical Data Manager", expanded=expanded):
        range_request = request
        status = MarketLakeDeveloperService(lake, provider).status(range_request)
        manifest = lake.get_manifest(provider, request.instrument_key, request.interval_minutes)
        details = {"Market Lake root": str(lake.root), "Provider": provider, "Instrument": request.instrument_key,
            "Interval": request.interval_minutes, "Period": f"{request.start_date} → {request.end_date}",
            "Manifest": None if manifest is None else manifest.dataset_id,
            "Raw schema version": lake.settings.raw_schema_version,
            "Intelligence schema version": lake.settings.intelligence_schema_version,
            "Outcome schema version": lake.settings.outcome_schema_version, "Engine version": status.engine_version,
            "Authentication": "Available" if manager and manager.authentication_available else "Unavailable",
            "Completed dates": status.completed_dates, "Failed dates": status.failed_dates}
        st.json(details)
        st.caption("Recommended pilot: NIFTY, 1 minute, 1 week, 5-minute analysis cadence.")
        st.info("Historical option-chain snapshots are unavailable for this sync. Records are CANDLE_ONLY_REPLAY.")
        rebuild = st.columns(3)
        redownload = rebuild[0].checkbox("Re-download Raw Data", value=False, key=PREFIX+"redownload")
        rebuild_intel = rebuild[1].checkbox("Rebuild Intelligence", value=False, key=PREFIX+"rebuild_intelligence")
        rebuild_outcomes = rebuild[2].checkbox("Rebuild Outcomes", value=False, key=PREFIX+"rebuild_outcomes")
        range_request = HistoricalRangeRequest(range_request.underlying, range_request.instrument_key,
            range_request.start_date, range_request.end_date, range_request.interval_minutes,
            include_options=False, rebuild_raw=redownload, rebuild_intelligence=rebuild_intel,
            rebuild_outcomes=rebuild_outcomes)
        if st.button("Preview Plan", key=PREFIX+"preview_plan", disabled=manager is None):
            try: st.session_state[PREFIX+"sync_plan"] = manager.preview_plan(range_request, cadence_minutes=cadence)
            except ValueError as error: st.error(str(error))
        plan = st.session_state.get(PREFIX+"sync_plan")
        if plan is not None:
            st.json({"Expected sessions": len(plan.expected_dates), "Raw sessions complete": len(plan.complete_dates),
                "Missing raw sessions": len(plan.missing_dates), "Intelligence sessions to build": len(plan.dates_to_enrich),
                "Outcome sessions to build": len(plan.dates_to_build_outcomes), "Estimated raw requests": plan.estimated_raw_requests,
                "Estimated analysis points": plan.estimated_analysis_points, "Analysis cadence minutes": cadence})
        def raw_action(_request):
            progress_box = st.empty()
            def report(value: HistoricalSyncProgress):
                st.session_state[PREFIX+"progress"] = value
                progress_box.json(asdict(value))
            result = manager.sync_missing_raw(_request, progress=report)
            st.session_state[PREFIX+"sync_result"] = result
            invalidate_historical_analytics_cache(st.session_state)
            return result
        callbacks = (("Sync Missing Raw Data", raw_action if manager else actions.sync_missing_data),
                     ("Retry Failed Dates", raw_action if manager else actions.sync_missing_data),
                     ("Build Intelligence", actions.build_intelligence), ("Build Outcomes", actions.build_outcomes))
        buttons = st.columns(4)
        for column, (label, callback) in zip(buttons, callbacks):
            if column.button(label, key=PREFIX+label.lower().replace(" ", "_"), disabled=callback is None):
                try:
                    callback(range_request); invalidate_historical_analytics_cache(st.session_state)
                    st.success(f"{label} completed through the Market Lake service.")
                except HistoricalAuthenticationError: st.error("Historical Upstox authentication failed.")
                except Exception: st.error(f"{label} failed. Review sanitized application logs.")
        if st.button("Reset UI Progress", key=PREFIX+"reset_progress"):
            for key in tuple(st.session_state):
                if key in (PREFIX+"sync_plan", PREFIX+"sync_result", PREFIX+"progress"): del st.session_state[key]
        progress = st.session_state.get(PREFIX+"progress")
        if progress is not None:
            st.subheader("Current progress")
            render_sync_progress(progress)
        sync_result = st.session_state.get(PREFIX+"sync_result")
        if sync_result is not None:
            st.subheader("Last sync result")
            _render_sync_result(sync_result)
        if not all(callback for _, callback in callbacks):
            st.caption("Maintenance actions require deployment-provided existing Market Lake service callbacks.")


def render_historical_analytics_workspace(underlyings: Mapping[str, str], *, provider: str = "upstox",
        lake: LocalHistoricalMarketLake | None = None, actions: MarketLakeActions = MarketLakeActions(),
        sync_manager: HistoricalSyncManager | None = None) -> None:
    """Render analytics without reading or writing replay/live session keys."""
    st.header("Historical Analytics")
    lake = lake or LocalHistoricalMarketLake(); service = HistoricalAnalyticsService(lake, provider=provider)
    row = st.columns(4)
    underlying = row[0].selectbox("Underlying", tuple(underlyings), key=PREFIX+"underlying")
    instrument = row[1].text_input("Instrument key", underlyings[underlying], key=PREFIX+"instrument_key")
    period = row[2].selectbox("Period", tuple(PeriodPreset), format_func=lambda item: item.value, key=PREFIX+"period")
    interval = row[3].selectbox("Interval", lake.settings.supported_intervals, key=PREFIX+"interval")
    custom_start = custom_end = None
    if period is PeriodPreset.CUSTOM:
        dates = st.columns(2)
        custom_start = dates[0].date_input("Custom Start Date", date.today()-timedelta(days=7), key=PREFIX+"custom_start")
        custom_end = dates[1].date_input("Custom End Date", date.today(), key=PREFIX+"custom_end")
    engine = st.text_input("Engine Version", lake.settings.engine_version, key=PREFIX+"engine_version") or None
    cadence = st.selectbox("Analysis cadence", lake.settings.supported_analysis_cadences, index=2,
        key=PREFIX+"analysis_cadence")
    with st.expander("Historical Analytics Filters", expanded=True):
        filters = st.columns(3)
        recommendation = filters[0].selectbox("Recommendation filter", ("ALL", "BUY CE", "BUY PE", "WAIT"), key=PREFIX+"recommendation")
        confidence = filters[1].slider("Confidence range", 0.0, 100.0, (0.0, 100.0), key=PREFIX+"confidence")
        compression = filters[2].slider("Compression range", 0.0, 100.0, (0.0, 100.0), key=PREFIX+"compression")
        positioning = _option("Positioning filter"); manipulation = _option("Manipulation filter")
        bias = _option("Institutional bias filter"); completeness = _option("Replay completeness filter")
    if st.button("Analyze Stored Data", type="primary", use_container_width=True, key=PREFIX+"analyze"):
        try:
            end = custom_end or date.today(); start, end = resolve_analytics_period(period, end, custom_start)
            request = HistoricalAnalyticsRequest(instrument, underlying, start, end, interval, engine,
                None if recommendation == "ALL" else recommendation, confidence[0], confidence[1],
                compression[0], compression[1], positioning, manipulation, bias, completeness)
            st.session_state[PREFIX+"result"] = service.analyze(request)
        except ValueError as error: st.error(str(error))
    end = custom_end or date.today(); start, end = resolve_analytics_period(period, end, custom_start)
    manager_request = HistoricalRangeRequest(underlying, instrument, start, end, interval, include_options=False)
    _developer_panel(lake, provider, manager_request, actions, sync_manager, cadence)
    result = st.session_state.get(PREFIX+"result")
    if not isinstance(result, HistoricalAnalyticsResult):
        st.info("Choose a range and click **Analyze Stored Data**. No data is downloaded automatically.")
        return
    _coverage(result)
    if result.explanations:
        for explanation in result.explanations: st.info(explanation)
    for title, values in _sections(result):
        with st.container(border=True):
            st.subheader(title); st.json(values)
            with st.expander("View Details"):
                st.dataframe(pd.DataFrame(result.detail_rows), hide_index=True, use_container_width=True)
    exports = st.columns(2)
    exports[0].download_button("Export CSV", service.export_csv(result), "historical_analytics.csv", "text/csv",
        key=PREFIX+"export_csv", use_container_width=True)
    exports[1].download_button("Export JSON", service.export_json(result), "historical_analytics.json", "application/json",
        key=PREFIX+"export_json", use_container_width=True)
