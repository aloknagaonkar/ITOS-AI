from pathlib import Path

from itos_platform.historical_analysis_orchestrator import HistoricalPipelineProgress


SOURCE = Path("ui/historical_analytics_workspace.py").read_text(encoding="utf-8")


def test_normal_workflow_is_explicit_and_date_only():
    assert 'st.header("Historical Analysis")' in SOURCE
    assert all(label in SOURCE for label in ('"Underlying"', '"From Date"', '"To Date"'))
    assert 'st.button("Download & Analyze"' in SOURCE
    assert 'st.button("Analyze Stored Data"' not in SOURCE


def test_advanced_controls_are_collapsed_and_normal_ui_has_no_json():
    assert 'st.expander("Advanced Developer Controls", expanded=False)' in SOURCE
    normal = SOURCE.split('with st.expander("Advanced Diagnostics')[0]
    assert "st.json(" not in normal


def test_progress_contract_clamps_percentages():
    progress = HistoricalPipelineProgress("run", "RUNNING", "PLAN", "RUNNING", 120, -1,
        None, "Planning", 1)
    assert progress.overall_percent == 100
    assert progress.stage_percent == 0

