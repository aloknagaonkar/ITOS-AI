from datetime import date
import json

import pytest

from itos_platform.historical_analysis_orchestrator import (
    HistoricalAnalysisOrchestrator, HistoricalAnalysisRunRequest,
    HistoricalAnalysisSettings, JsonRunCheckpointStore, PipelineStage,
)


def request(**changes):
    values = dict(underlying="NIFTY", instrument_key="NSE_INDEX|Nifty 50",
        start_date=date(2026, 7, 1), end_date=date(2026, 7, 3))
    values.update(changes)
    return HistoricalAnalysisRunRequest(**values)


def test_request_validation_rejects_invalid_future_range_and_instrument():
    settings = HistoricalAnalysisSettings(maximum_date_range_days=5)
    supported = {"NIFTY": "NSE_INDEX|Nifty 50"}
    with pytest.raises(ValueError): request(start_date=date(2026, 7, 3), end_date=date(2026, 7, 1)).validate(settings, supported)
    with pytest.raises(ValueError): request(end_date=date(2026, 8, 4)).validate(settings, supported, today=date(2026, 8, 3))
    with pytest.raises(ValueError): request(instrument_key="wrong").validate(settings, supported)


def test_one_click_pipeline_order_progress_and_analytics(tmp_path):
    calls, progress = [], []
    def operation(name, value=None):
        def run(_request): calls.append(name); return value
        return run
    orchestrator = HistoricalAnalysisOrchestrator(
        sync_underlying=operation("raw"), download_options=operation("options"),
        build_intelligence=operation("intelligence"), build_outcomes=operation("outcomes"),
        build_index=operation("index"), prepare_analytics=operation("analytics", {"ready": True}),
        checkpoint_store=JsonRunCheckpointStore(tmp_path))
    result = orchestrator.run(request(), progress_callback=progress.append, run_id="stable")
    assert calls == ["raw", "options", "intelligence", "outcomes", "index", "analytics"]
    assert [item.stage for item in progress] == [stage.value for stage in PipelineStage]
    assert [item.overall_percent for item in progress] == sorted(item.overall_percent for item in progress)
    assert result.analytics == {"ready": True} and result.run_id == "stable"
    payload = json.loads((tmp_path / "stable.json").read_text())
    assert "token" not in json.dumps(payload).lower()


def test_option_failure_is_partial_and_does_not_block_analysis():
    calls = []
    def options(_): raise RuntimeError("Option API unavailable")
    def later(_): calls.append(True)
    result = HistoricalAnalysisOrchestrator(sync_underlying=later, download_options=options,
        build_intelligence=later, build_outcomes=later, build_index=later,
        prepare_analytics=lambda _: "ready").run(request())
    assert result.status == "PARTIAL"
    assert result.analytics == "ready"
    assert len(calls) == 4


def test_cancel_preserves_checkpoint_without_running_operations(tmp_path):
    calls = []
    orchestrator = HistoricalAnalysisOrchestrator(sync_underlying=lambda _: calls.append(1),
        checkpoint_store=JsonRunCheckpointStore(tmp_path))
    orchestrator.cancel_after_current_date()
    result = orchestrator.run(request(), run_id="cancelled")
    assert result.status == "CANCELLED" and not calls
    assert (tmp_path / "cancelled.json").exists()


def test_weekends_are_safely_skipped():
    result = HistoricalAnalysisOrchestrator(sync_underlying=lambda _: None).run(
        request(start_date=date(2026, 7, 4), end_date=date(2026, 7, 6)))
    assert result.progress.skipped_dates == (date(2026, 7, 4), date(2026, 7, 5))

