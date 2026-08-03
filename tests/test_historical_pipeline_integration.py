from dataclasses import replace
from datetime import date, datetime

import pandas as pd

from itos_platform.historical_pipeline import HistoricalPointInTimeRunner, compose_historical_pipeline
from itos_platform.market_lake import HistoricalIntelligenceRecord, MarketLakeSettings
from itos_platform.replay import DataMode, ReplayRequest


def record():
    stamp = datetime.fromisoformat("2025-01-02T10:00:00+05:30")
    return HistoricalIntelligenceRecord(
        "upstox", "NIFTY", "NIFTY", 1, stamp.date(), stamp, stamp, stamp,
        "itos-18.4c-v1", "intelligence-v1", "CANDLE_ONLY_REPLAY",
        recommendation="WAIT", values={"recommendation": "WAIT"},
    )


def test_composition_shares_one_lake_and_index(tmp_path):
    pipeline = compose_historical_pipeline(root=tmp_path)
    assert pipeline.sync_manager.market_lake is pipeline.lake
    assert pipeline.runner.lake is pipeline.lake
    assert pipeline.live_capture.lake is pipeline.lake
    assert pipeline.finalization.lake is pipeline.lake
    assert pipeline.index_service.index is pipeline.index
    assert pipeline.similarity_service.index is pipeline.index


def test_real_index_build_and_diagnostics(tmp_path):
    pipeline = compose_historical_pipeline(root=tmp_path)
    pipeline.lake.store_intelligence_records((record(),))
    request = type("Request", (), {"instrument_key": "NIFTY", "start_date": date(2025, 1, 2),
        "end_date": date(2025, 1, 2), "interval_minutes": 1})()
    result = pipeline.build_index(request)
    assert result.completed == 1
    assert pipeline.index.count() == 1
    assert pipeline.index.integrity_diagnostics()["integrity"] == "ok"


def test_point_in_time_runner_invokes_application_once_without_live_state(tmp_path):
    pipeline = compose_historical_pipeline(root=tmp_path)
    calls = []
    expected = object()

    class Application:
        def __init__(self, **kwargs):
            assert kwargs["provider"].mode is DataMode.HISTORICAL_REPLAY

        def execute(self, **kwargs):
            calls.append(kwargs)
            return expected

    runner = HistoricalPointInTimeRunner(pipeline.lake, application_factory=Application)
    request = ReplayRequest("NIFTY", "NIFTY", date(2025, 1, 2),
                            datetime.fromisoformat("2025-01-02T10:00:00+05:30"), 1,
                            requested_option_snapshot=False)
    assert runner(request) is expected
    assert len(calls) == 1
    assert calls[0]["data_mode"] is DataMode.HISTORICAL_REPLAY
    assert calls[0]["session_state"] == {}
    assert calls[0]["should_load"] is False
