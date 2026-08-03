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
from itos_platform.historical_trade_review import (
    NAVIGATION_REGISTRY, TradeReviewFilters, build_coverage_rows, build_trade_reviews,
    export_csv as export_review_csv, export_json as export_review_json,
    filter_trade_reviews, trade_table_rows,
)
from itos_platform.historical_intelligence_index import make_trade_id
from itos_platform.historical_analysis_orchestrator import (
    HistoricalAnalysisOrchestrator, HistoricalAnalysisRunRequest,
    HistoricalAnalysisSettings, HistoricalPipelineProgress, JsonRunCheckpointStore,
)

PREFIX = "historical_analytics_"
TRADE_PREFIX = "historical_trade_review_"


@dataclass(frozen=True)
class MarketLakeActions:
    """Existing orchestration callbacks supplied by deployment, never recreated here."""
    sync_missing_data: Callable[[HistoricalRangeRequest], object] | None = None
    build_intelligence: Callable[[HistoricalRangeRequest], object] | None = None
    build_outcomes: Callable[[HistoricalRangeRequest], object] | None = None
    build_index: Callable[[HistoricalRangeRequest], object] | None = None
    validate_index: Callable[[HistoricalRangeRequest], object] | None = None
    rebuild_outdated: Callable[[HistoricalRangeRequest], object] | None = None
    finalize_today: Callable[[HistoricalRangeRequest], object] | None = None
    download_options: Callable[[HistoricalRangeRequest], object] | None = None
    index_status: Callable[[HistoricalRangeRequest], object] | None = None


def _option(label: str) -> str | None:
    value = st.text_input(label, key=PREFIX+label.lower().replace(" ", "_"))
    return value.strip() or None


def _coverage(result: HistoricalAnalyticsResult) -> None:
    st.subheader("Historical Data Coverage")
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
    st.caption("Available dates: " + (", ".join(map(str, result.available_dates)) or "None"))
    st.caption("Missing dates: " + (", ".join(map(str, result.missing_dates)) or "None"))
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
    notes = [*(values.get("quality_flags") or ()), *(values.get("explanations") or ())]
    if notes: st.dataframe(pd.DataFrame({"Status detail": notes}), hide_index=True, use_container_width=True)


def render_pipeline_progress(progress: HistoricalPipelineProgress) -> None:
    """Render only explicit immutable fields (never raw/custom-object output)."""
    st.subheader("Historical Analysis Progress")
    st.progress(progress.overall_percent / 100.0, text=f"Overall Progress: {progress.overall_percent:.1f}%")
    metrics = st.columns(4)
    metrics[0].metric("Current Stage", progress.stage.replace("_", " ").title())
    metrics[1].metric("Current Date", str(progress.current_date or "—"))
    metrics[2].metric("Status", progress.overall_status.title())
    metrics[3].metric("Requested Dates", progress.expected_dates)
    st.caption(progress.status_message)
    st.dataframe(pd.DataFrame([{
        "Date": row.trading_date, "Trading Session Status": row.session.replace("_", " ").title(),
        "Underlying Data": row.underlying, "Historical Options": row.options,
        "Intelligence": row.intelligence, "Outcomes": row.outcomes, "Index": row.index,
        "Final Status": row.final, "Action / Explanation": row.explanation,
    } for row in progress.date_statuses]), hide_index=True, use_container_width=True)


def _render_sync_result(result: object) -> None:
    """Render a stored result without passing a runtime object to Streamlit."""
    if isinstance(result, pd.DataFrame):
        st.dataframe(result, hide_index=True, use_container_width=True)
    elif is_dataclass(result) and not isinstance(result, type):
        st.dataframe(pd.DataFrame(asdict(result).items(), columns=("Result", "Value")), hide_index=True)
    elif isinstance(result, Mapping):
        st.dataframe(pd.DataFrame(dict(result).items(), columns=("Result", "Value")), hide_index=True)
    else:
        model_dump = getattr(result, "model_dump", None)
        values = model_dump() if callable(model_dump) else {"status": "Unavailable"}
        st.dataframe(pd.DataFrame(values.items(), columns=("Result", "Value")), hide_index=True)


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
        st.dataframe(pd.DataFrame(details.items(), columns=("Property", "Value")), hide_index=True, use_container_width=True)
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
            st.dataframe(pd.DataFrame({"Metric": ["Expected sessions","Raw sessions complete","Missing raw sessions","Intelligence sessions to build","Outcome sessions to build","Estimated raw requests","Estimated analysis points","Analysis cadence minutes"], "Value": [len(plan.expected_dates),len(plan.complete_dates),len(plan.missing_dates),len(plan.dates_to_enrich),len(plan.dates_to_build_outcomes),plan.estimated_raw_requests,plan.estimated_analysis_points,cadence]}), hide_index=True, use_container_width=True)
        def raw_action(_request):
            progress_box = st.empty()
            def report(value: HistoricalSyncProgress):
                st.session_state[PREFIX+"progress"] = value
                progress_box.dataframe(pd.DataFrame(asdict(value).items(), columns=("Progress", "Value")), hide_index=True)
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
        index_callbacks = (
            ("Build Missing Index", actions.build_index),
            ("Validate Index", actions.validate_index),
            ("Rebuild Outdated Fingerprints", actions.rebuild_outdated),
            ("Finalize Today", actions.finalize_today),
        )
        index_buttons = st.columns(4)
        for column, (label, callback) in zip(index_buttons, index_callbacks):
            if column.button(label, key=PREFIX+label.lower().replace(" ", "_"), disabled=callback is None):
                try:
                    value = callback(range_request)
                    st.session_state[PREFIX+"maintenance_result"] = value
                    st.success(f"{label} completed.")
                except Exception:
                    st.error(f"{label} could not complete; stored data and index were not corrupted.")
        if actions.index_status is not None:
            try:
                index_status = actions.index_status(range_request)
                st.subheader("Historical Pipeline Status")
                st.dataframe(pd.DataFrame(index_status.items(), columns=("Stage", "Status")),
                             hide_index=True, use_container_width=True)
            except Exception:
                st.warning("Historical index diagnostics are temporarily unavailable (the database may be locked).")
        if actions.download_options is not None and st.button(
                "Download Historical Options", key=PREFIX+"download_historical_options"):
            try:
                st.session_state[PREFIX+"option_result"] = actions.download_options(range_request)
                st.success("Historical option candle download completed.")
            except Exception:
                st.warning("Historical options are unavailable; underlying analytics remains available.")
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
        sync_manager: HistoricalSyncManager | None = None,
        open_similarity: Callable[[str], None] | None = None) -> None:
    """Render analytics without reading or writing replay/live session keys."""
    st.header("Historical Analysis")
    lake = lake or LocalHistoricalMarketLake(); service = HistoricalAnalyticsService(lake, provider=provider)
    settings = HistoricalAnalysisSettings(maximum_date_range_days=lake.settings.maximum_sync_range)
    row = st.columns(3)
    underlying = row[0].selectbox("Underlying", tuple(underlyings), key="historical_simple_ui_underlying")
    start = row[1].date_input("From Date", date.today()-timedelta(days=7), key="historical_simple_ui_from_date")
    end = row[2].date_input("To Date", date.today(), key="historical_simple_ui_to_date")
    instrument, interval, cadence = underlyings[underlying], 1, 5
    include_options, rebuild_intel, rebuild_outcomes, rebuild_index = True, False, False, False
    with st.expander("Advanced Developer Controls", expanded=False):
        instrument = st.text_input("Instrument key", instrument, key="historical_simple_ui_instrument_key")
        advanced = st.columns(3)
        interval = advanced[0].selectbox("Interval", lake.settings.supported_intervals, key="historical_simple_ui_interval")
        cadence = advanced[1].selectbox("Analysis cadence", lake.settings.supported_analysis_cadences,
            index=2, key="historical_simple_ui_cadence")
        include_options = advanced[2].checkbox("Historical options", True, key="historical_simple_ui_options")
        rebuild_intel = st.checkbox("Rebuild intelligence", False, key="historical_simple_ui_rebuild_intelligence")
        rebuild_outcomes = st.checkbox("Rebuild outcomes", False, key="historical_simple_ui_rebuild_outcomes")
        rebuild_index = st.checkbox("Rebuild index", False, key="historical_simple_ui_rebuild_index")
    if st.button("Download & Analyze", type="primary", use_container_width=True,
                 key="historical_simple_ui_download_analyze"):
        try:
            run_request = HistoricalAnalysisRunRequest(underlying, instrument, start, end, interval, cadence,
                include_options, True, rebuild_intel, rebuild_outcomes, rebuild_index)
            run_request.validate(settings, underlyings)
            def prepare(range_request):
                return service.analyze(HistoricalAnalyticsRequest(instrument, underlying, start, end, interval))
            orchestrator = HistoricalAnalysisOrchestrator(
                sync_underlying=(sync_manager.sync_missing_raw if sync_manager else actions.sync_missing_data),
                download_options=actions.download_options,
                build_intelligence=actions.build_intelligence, build_outcomes=actions.build_outcomes,
                build_index=actions.build_index, prepare_analytics=prepare,
                checkpoint_store=JsonRunCheckpointStore(lake.root / "runs"), settings=settings)
            def report(value):
                st.session_state["historical_pipeline_progress_current"] = value
                render_pipeline_progress(value)
            run = orchestrator.run(run_request, progress_callback=report)
            st.session_state["historical_pipeline_run_active"] = run
            st.session_state["historical_pipeline_results_current"] = run.analytics
            st.session_state[PREFIX+"result"] = run.analytics
        except ValueError as error: st.error(str(error))
        except HistoricalAuthenticationError: st.error("Authentication required before historical data can be downloaded.")
        except Exception: st.error("Historical Analysis could not start. Review Advanced Diagnostics.")
    manager_request = HistoricalRangeRequest(underlying, instrument, start, end, interval, include_options=False)
    _developer_panel(lake, provider, manager_request, actions, sync_manager, cadence)
    progress = st.session_state.get("historical_pipeline_progress_current")
    if isinstance(progress, HistoricalPipelineProgress): render_pipeline_progress(progress)
    result = st.session_state.get(PREFIX+"result")
    if not isinstance(result, HistoricalAnalyticsResult):
        st.info("Choose an underlying and dates, then click **Download & Analyze**. Nothing runs before that click.")
        return
    _coverage(result)
    manifest = lake.get_manifest(provider, instrument, interval)
    expected = tuple(start + timedelta(days=i) for i in range((end-start).days+1)
                     if (start + timedelta(days=i)).weekday() < 5)
    coverage_rows = build_coverage_rows(manifest, expected)
    st.dataframe(pd.DataFrame([{
        "Date": row.trading_date, "Underlying Candles": "Yes" if row.underlying_candles else "—",
        "Option Contracts": "Yes" if row.option_contracts else "—", "Intelligence": "Yes" if row.intelligence else "—",
        "Outcomes": "Yes" if row.outcomes else "—", "Replay Completeness": row.replay_completeness,
        "Status": row.status, "Action Required": row.action_required} for row in coverage_rows]),
        hide_index=True, use_container_width=True)
    st.caption("All dependent stages ran automatically after the explicit Download & Analyze action.")
    if result.explanations:
        for explanation in result.explanations: st.info(explanation)
    st.header("Historical Dashboard")
    for title, values in _sections(result):
        with st.container(border=True):
            st.subheader(title)
            safe = [(str(key).replace("_", " ").title(), "—" if value is None else value)
                    for key, value in values.items()]
            columns = st.columns(min(4, max(1, len(safe))))
            for index, (label, value) in enumerate(safe):
                if isinstance(value, (str, int, float, bool)): columns[index % len(columns)].metric(label, value)
                else: columns[index % len(columns)].caption(f"**{label}:** {value or '—'}")
            with st.expander("View Details"):
                st.dataframe(pd.DataFrame(result.detail_rows), hide_index=True, use_container_width=True)

    st.header("Historical Trade Review")
    reviews = build_trade_reviews(result.records, result.outcome_records, manifest.option_dates if manifest else ())
    with st.expander("Trade Review Filters", expanded=True):
        fcols = st.columns(4)
        decisions = tuple(fcols[0].multiselect("Decision", ("BUY CE","BUY PE","WAIT"), key=TRADE_PREFIX+"decisions"))
        classifications = tuple(fcols[1].multiselect("Result Classification", ("FAVOURABLE","UNFAVOURABLE","INCONCLUSIVE","AVOIDED","MISSED_OPPORTUNITY","NOT_EVALUABLE"), key=TRADE_PREFIX+"classifications"))
        confidence_filter = fcols[2].slider("Confidence Range",0.0,100.0,(0.0,100.0),key=TRADE_PREFIX+"confidence")
        trigger_status = fcols[3].selectbox("Trigger Checklist Status",("ALL","PASS","PARTIAL","FAIL","UNAVAILABLE"),key=TRADE_PREFIX+"trigger_status")
        searches=st.columns(2)
        contract_search=searches[0].text_input("Contract / Strike Search",key=TRADE_PREFIX+"contract_search")
        reason_search=searches[1].text_input("Reason Search",key=TRADE_PREFIX+"reason_search")
    filtered=filter_trade_reviews(reviews,TradeReviewFilters(start,end,decisions,classifications,confidence_filter[0],confidence_filter[1],None if trigger_status=="ALL" else trigger_status,contract_search=contract_search,reason_search=reason_search))
    counts={name:sum(r.outcome_classification==name for r in filtered) for name in ("FAVOURABLE","UNFAVOURABLE","INCONCLUSIVE","AVOIDED","MISSED_OPPORTUNITY","NOT_EVALUABLE")}
    cards=st.columns(4)
    summary=("Total Setups",len(filtered)),("Favourable",counts["FAVOURABLE"]),("Unfavourable",counts["UNFAVOURABLE"]),("Inconclusive",counts["INCONCLUSIVE"]),("Avoided",counts["AVOIDED"]),("Missed Opportunity",counts["MISSED_OPPORTUNITY"]),("Not Evaluable",counts["NOT_EVALUABLE"]),("Average Confidence",round(sum(r.decision_confidence or 0 for r in filtered)/len([r for r in filtered if r.decision_confidence is not None]),1) if any(r.decision_confidence is not None for r in filtered) else "—")
    for i,(label,value) in enumerate(summary): cards[i%4].metric(label,value)
    table=pd.DataFrame(trade_table_rows(filtered))
    if table.empty: st.info("No stored historical setups match the selected filters.")
    else:
        edited=st.data_editor(table,hide_index=True,use_container_width=True,disabled=[c for c in table.columns if c!="View Details"],key=TRADE_PREFIX+"table")
        selected=edited.loc[edited["View Details"]==True,"Record ID"].tolist()
        if selected: st.session_state[TRADE_PREFIX+"selected_record_id"]=selected[-1]
    exports=st.columns(2)
    exports[0].download_button("Export Filtered CSV",export_review_csv(filtered),"historical_trade_review.csv","text/csv",key=TRADE_PREFIX+"export_csv",use_container_width=True)
    exports[1].download_button("Export Filtered JSON",export_review_json(filtered),"historical_trade_review.json","application/json",key=TRADE_PREFIX+"export_json",use_container_width=True)

    selected_trade_id = st.session_state.pop(TRADE_PREFIX+"selected_trade_id", None)
    if selected_trade_id:
        matching = next((item for item in result.records if make_trade_id(item) == selected_trade_id), None)
        if matching is not None:
            st.session_state[TRADE_PREFIX+"selected_record_id"] = matching.record_id
    selected_id=st.session_state.get(TRADE_PREFIX+"selected_record_id")
    selected=next((item for item in reviews if item.record_id==selected_id),None)
    st.header("Selected Trade Deep Dive")
    if selected is None: st.info("Select View Details in the Historical Trade Review table.")
    else:
        if st.button("Back to Historical Trade Table",key=TRADE_PREFIX+"back_to_table"):
            st.session_state[TRADE_PREFIX+"selected_record_id"]=None
        st.subheader(f"Frozen {selected.recommendation} decision — {selected.analysis_timestamp}")
        source_record = next((item for item in result.records if item.record_id == selected.record_id), None)
        if source_record is not None and open_similarity is not None:
            if st.button("Find Similar Trades", type="primary", key=TRADE_PREFIX+"find_similar"):
                open_similarity(make_trade_id(source_record))
        st.caption(selected.outcome_reason+" This is a historical directional evaluation, not a real trade result.")
        st.markdown("**Why it was considered**")
        for evidence in [e for t in selected.trigger_results for e in t.evidence if t.status=="PASS"]: st.markdown(f"- {e}")
        st.markdown("**Why it worked or failed**")
        st.markdown(f"- {selected.primary_success_reason or selected.primary_failure_reason or selected.outcome_reason}")
        for trigger in selected.trigger_results:
            with st.expander(f"{trigger.display_name} — {trigger.status}",expanded=st.session_state.get(TRADE_PREFIX+"active_analysis_target")==trigger.analysis_target):
                st.caption(f"Impact: {trigger.impact}")
                for evidence in trigger.evidence: st.markdown(f"- {evidence}")
                if trigger.missing_requirement: st.warning("Missing requirement: "+trigger.missing_requirement)
                if trigger.fix_required: st.info("Fix required: "+trigger.fix_required)
                st.caption("Stable analysis target: "+trigger.analysis_target)
                if trigger.status != "PASS" and st.button("View Analysis",key=TRADE_PREFIX+"target_"+trigger.trigger_id):
                    st.session_state[TRADE_PREFIX+"active_analysis_target"]=trigger.analysis_target

    st.header("Historical Option Data")
    st.info("Derived historical chains align expired-contract candles. They are not complete historical exchange option-chain snapshots.")
    option_days=set(manifest.option_dates if manifest else ())
    st.dataframe(pd.DataFrame([{"Date":d,"Historical option contracts discovered":"Stored" if d in option_days else "—","Bid/Ask availability":"Historical bid/ask unavailable","IV availability":"Historical IV unavailable","Greeks availability":"Historical Greeks unavailable","Derived Chain availability":"PARTIAL_OPTION_REPLAY" if d in option_days else "UNAVAILABLE"} for d in expected]),hide_index=True,use_container_width=True)

    with st.expander("Advanced Diagnostics — Developer Only",expanded=False):
        st.caption("Raw Stored Record → JSON")
        if selected is not None: st.json(asdict(selected))
        else: st.info("Select a record to inspect its sanitized frozen payload.")
