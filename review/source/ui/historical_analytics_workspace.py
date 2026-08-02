"""Streamlit presentation for the isolated Historical Analytics workspace."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Mapping

import pandas as pd
import streamlit as st

from itos_platform.historical_analytics import (
    HistoricalAnalyticsRequest, HistoricalAnalyticsResult, HistoricalAnalyticsService,
    resolve_analytics_period,
)
from itos_platform.market_lake import (
    HistoricalRangeRequest, LocalHistoricalMarketLake, MarketLakeDeveloperService, PeriodPreset,
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


def _developer_panel(lake: LocalHistoricalMarketLake, provider: str, result: HistoricalAnalyticsResult,
                     actions: MarketLakeActions) -> None:
    expanded = bool(st.session_state.get(PREFIX+"developer_open", False))
    with st.expander("Developer → Market Lake", expanded=expanded):
        request = result.request
        range_request = HistoricalRangeRequest(request.underlying, request.instrument_key, request.start_date,
            request.end_date, request.interval_minutes)
        status = MarketLakeDeveloperService(lake, provider).status(range_request)
        manifest = lake.get_manifest(provider, request.instrument_key, request.interval_minutes)
        details = {"Market Lake root": str(lake.root), "Provider": provider, "Instrument": request.instrument_key,
            "Interval": request.interval_minutes, "Period": f"{request.start_date} → {request.end_date}",
            "Manifest": None if manifest is None else manifest.dataset_id,
            "Raw schema version": lake.settings.raw_schema_version,
            "Intelligence schema version": lake.settings.intelligence_schema_version,
            "Outcome schema version": lake.settings.outcome_schema_version, "Engine version": status.engine_version,
            "Raw sessions": result.raw_session_count, "Intelligence sessions": result.intelligence_session_count,
            "Outcome sessions": result.outcome_session_count, "Option sessions": result.option_session_count,
            "Completed dates": status.completed_dates, "Missing dates": result.missing_dates, "Failed dates": status.failed_dates}
        st.json(details)
        buttons = st.columns(3)
        callbacks = (("Sync Missing Data", actions.sync_missing_data), ("Build Intelligence", actions.build_intelligence),
                     ("Build Outcomes", actions.build_outcomes))
        for column, (label, callback) in zip(buttons, callbacks):
            if column.button(label, key=PREFIX+label.lower().replace(" ", "_"), disabled=callback is None):
                callback(range_request)
                st.success(f"{label} requested through the existing Market Lake service.")
        if not all(callback for _, callback in callbacks):
            st.caption("Maintenance actions require deployment-provided existing Market Lake service callbacks.")


def render_historical_analytics_workspace(underlyings: Mapping[str, str], *, provider: str = "upstox",
        lake: LocalHistoricalMarketLake | None = None, actions: MarketLakeActions = MarketLakeActions()) -> None:
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
    _developer_panel(lake, provider, result, actions)
