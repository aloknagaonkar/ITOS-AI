"""Streamlit adapter for read-only Historical Analytics."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Mapping

import pandas as pd
import streamlit as st

from itos_platform.historical_analytics import AnalyticsFilters, HistoricalAnalyticsService, PERIOD_LABELS
from itos_platform.market_lake import HistoricalRangeRequest, LocalHistoricalMarketLake, MarketLakeDeveloperService


def render_historical_analytics_workspace(underlyings: Mapping[str, str], *, provider: str = "upstox") -> None:
    st.header("Historical Analytics")
    lake = LocalHistoricalMarketLake(); service = HistoricalAnalyticsService(lake, provider=provider)
    c1, c2 = st.columns(2)
    underlying = c1.selectbox("Underlying", tuple(underlyings), key="analytics_underlying")
    period = c2.selectbox("Period", tuple(PERIOD_LABELS), key="analytics_period")
    end = date.today(); start = None
    if period == "Custom Range":
        c3, c4 = st.columns(2)
        start = c3.date_input("Start Date", end-timedelta(days=7), key="analytics_start")
        end = c4.date_input("End Date", end, key="analytics_end")
    with st.expander("Filters and Search"):
        f1, f2, f3 = st.columns(3)
        recommendation = f1.selectbox("Recommendation", ("All", "BUY CE", "BUY PE", "WAIT"))
        confidence = f2.slider("Confidence Range", 0, 100, (0, 100))
        compression = f3.slider("Compression Range", 0, 100, (0, 100))
        f4, f5, f6 = st.columns(3)
        manipulation = f4.text_input("Manipulation") or None
        positioning = f5.text_input("Positioning") or None
        bias = f6.text_input("Institutional Bias") or None
        completeness = st.selectbox("Replay Completeness", ("All", "FULL_REPLAY", "PARTIAL_OPTION_REPLAY", "CANDLE_ONLY_REPLAY"))
        search = st.text_input("Search date, time, recommendation or confidence")
    if st.button("Analyze", type="primary", use_container_width=True):
        try:
            filters = AnalyticsFilters(None if recommendation == "All" else recommendation,
                confidence[0], confidence[1], compression[0], compression[1], manipulation,
                positioning, bias, None if completeness == "All" else completeness, search)
            st.session_state["historical_analytics_result"] = service.analyze(underlying=underlying,
                instrument_key=underlyings[underlying], period=period, start_date=start, end_date=end, filters=filters)
        except ValueError as exc: st.error(str(exc))
    result = st.session_state.get("historical_analytics_result")
    if result is None: st.info("Select a period and click **Analyze**. Stored Market Lake data will be used."); return
    header = result.header
    columns = st.columns(4)
    for index, (label, value) in enumerate((("Underlying", header.underlying), ("Selected Period", header.selected_period),
        ("Trading Days", header.trading_days), ("Analysis Points", header.analysis_points), ("Engine Version", header.engine_version),
        ("Data Completeness", f"{header.data_completeness:.1f}%"), ("Option Completeness", f"{header.option_completeness:.1f}%"),
        ("Market Lake Status", header.market_lake_status))): columns[index % 4].metric(label, value)
    if header.missing_dates:
        st.warning("The selected period is incomplete. Analytics shows available stored records only.")
        st.write("Available Dates", header.available_dates); st.write("Missing Dates", header.missing_dates)
        st.write("Option Availability", f"{header.option_completeness:.1f}%")
        st.info("Use **Developer → Market Lake → Sync Missing Data** to fill gaps. Nothing was downloaded automatically.")
    for title, values in result.cards.items():
        with st.container(border=True):
            st.subheader(title.replace("_", " ").title()); st.json(values)
            with st.expander("View Details"): st.dataframe(pd.DataFrame(result.detail_rows), hide_index=True, use_container_width=True)
    e1, e2 = st.columns(2)
    e1.download_button("Export CSV", service.export_csv(result), "historical_analytics.csv", "text/csv", use_container_width=True)
    try: parquet = service.export_parquet(result)
    except (ImportError, ValueError): parquet = None
    e2.download_button("Export Parquet", parquet or b"", "historical_analytics.parquet",
                       "application/octet-stream", disabled=parquet is None, use_container_width=True)

    with st.expander("Developer → Market Lake"):
        request = HistoricalRangeRequest(underlying, underlyings[underlying], start or end-timedelta(days=6), end)
        status = MarketLakeDeveloperService(lake, provider).status(request)
        st.caption("Maintenance actions are explicit and never run during Analyze.")
        d1, d2, d3 = st.columns(3)
        d1.button("Sync Missing Data", disabled=True); d2.button("Build Intelligence", disabled=True); d3.button("Build Outcomes", disabled=True)
        manifest = lake.get_manifest(provider, request.instrument_key, request.interval_minutes)
        st.json({"Manifest": None if manifest is None else manifest.dataset_id, "Schema Version": lake.settings.intelligence_schema_version,
            "Engine Version": status.engine_version, "Storage Size": sum(p.stat().st_size for p in lake.root.rglob("*") if p.is_file()) if lake.root.exists() else 0,
            "Completed Dates": status.completed_dates, "Failed Dates": status.failed_dates})
