from dataclasses import dataclass
from datetime import date
import logging
from types import SimpleNamespace as Result

import pandas as pd

from itos_platform.historical_analysis_orchestrator import HistoricalAnalysisOrchestrator, HistoricalAnalysisRunRequest
from itos_platform.historical_pipeline_observability import (
    HistoricalPipelineObserver, generate_run_id, normalize_dataframe,
)
from ui.historical_analytics_workspace import pipeline_diagnostics_rows


DAY = date(2026, 7, 30)


def test_run_id_generation_is_short_uppercase_and_unique():
    values = {generate_run_id() for _ in range(20)}
    assert len(values) == 20
    assert all(len(value) == 6 and value.isalnum() and value == value.upper() for value in values)


def test_structured_stage_date_duration_exception_and_persistent_log(tmp_path):
    observer = HistoricalPipelineObserver("AB12CD", log_root=tmp_path, stall_threshold_seconds=-1)
    observer.log("Download & Analyze clicked", authorization="Bearer-secret")
    observer.stage_started("PLAN", (DAY,)); observer.date_status(DAY, "PLAN", "existing", rows_stored=375)
    observer.stage_completed("PLAN", (DAY,))
    try: raise RuntimeError("provider broke")
    except RuntimeError as error: observer.stage_failed("DOWNLOAD_OPTIONS", error, day=DAY)
    assert observer.validate_stall("PLAN", DAY, 1, "calendar lookup")
    path = observer.log_path; observer.close(); content = path.read_text()
    assert "PLAN started" in content and "PLAN completed" in content and "duration_seconds=" in content
    assert "date=2026-07-30" in content and "status=existing" in content
    assert "RuntimeError" in content and "Traceback" in content and "Possible stalled stage" in content
    assert "Bearer-secret" not in content and "[REDACTED]" in content


def test_orchestrator_entry_exit_and_all_stages_are_logged(tmp_path):
    def raw(request): return Result(completed_dates=(request.start_date,), skipped_dates=(), no_data_dates=(),
        downloaded_row_count=1, stored_row_count=1)
    def observer_factory(run_id, **kwargs): return HistoricalPipelineObserver(run_id, log_root=tmp_path, stall_threshold_seconds=99)
    request = HistoricalAnalysisRunRequest("NIFTY", "NIFTY", DAY, DAY, include_historical_options=False)
    run = HistoricalAnalysisOrchestrator(sync_underlying=raw, observer_factory=observer_factory).run(request, run_id="ENTRY1")
    content = next(tmp_path.rglob("run_ENTRY1.log")).read_text()
    assert "orchestrator.run() called" in content and "orchestrator.run() returned" in content
    assert "PREPARE_ANALYTICS skipped reason=operation unavailable; analytics not executed" in content
    assert run.diagnostics.stage_durations["TOTAL"] >= 0


@dataclass
class ComplexMetric:
    score: int


def test_dataframe_normalization_removes_custom_objects():
    normalized = normalize_dataframe(pd.DataFrame({"metric": [ComplexMetric(7)], "items": [[1, 2]]}))
    assert normalized.iloc[0, 0] == "{'score': 7}"
    assert normalized.iloc[0, 1] == "1, 2"


def test_developer_diagnostics_has_all_required_read_only_fields(tmp_path):
    request = HistoricalAnalysisRunRequest("NIFTY", "NIFTY", DAY, DAY)
    def raw(_request): return Result(completed_dates=(DAY,), skipped_dates=(), no_data_dates=())
    def factory(run_id, **kwargs): return HistoricalPipelineObserver(run_id, log_root=tmp_path)
    progress = HistoricalAnalysisOrchestrator(sync_underlying=raw, observer_factory=factory).run(request).progress
    labels = {row["Diagnostic"] for row in pipeline_diagnostics_rows(progress)}
    assert {"Run ID", "Current Stage", "Last Completed Stage", "Current Date", "Last Successful Date",
        "Elapsed Time", "Current Progress", "Completed Dates", "Failed Dates", "Skipped Dates",
        "Partial Dates", "Last Exception", "Stage Durations", "Checkpoint Path", "Resume Available"} == labels
