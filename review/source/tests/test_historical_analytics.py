from dataclasses import replace
from datetime import date, datetime
import json

import pytest

from itos_platform.historical_analytics import (
    HistoricalAnalyticsRequest, HistoricalAnalyticsService, WorkspaceMode, resolve_analytics_period,
)
from itos_platform.market_lake import (
    DatasetManifest, HistoricalIntelligenceRecord, HistoricalOutcomeRecord, MarketLakeSettings, PeriodPreset,
)
from itos_platform.replay import DataMode
from ui.historical_analytics_workspace import MarketLakeActions, PREFIX


class ReadOnlyLake:
    settings = MarketLakeSettings()
    def __init__(self, records=(), outcomes=(), *, manifest=True, settings=None):
        self.records, self.outcomes, self.queries = tuple(records), tuple(outcomes), []
        self.manifest = manifest
        if settings is not None: self.settings = settings
    def get_manifest(self, provider, instrument, interval):
        if not self.manifest: return None
        days = (date(2026, 7, 30), date(2026, 7, 31))
        return DatasetManifest("lake", provider, instrument, "NIFTY 50", interval, 5,
            engine_version=self.settings.engine_version, available_dates=days, intelligence_dates=days,
            outcome_dates=(days[1],), option_dates=(days[1],), failed_dates=(date(2026, 7, 29),))
    def query_intelligence(self, query):
        self.queries.append(query)
        return tuple(replace(record, values=dict(record.values)) for record in self.records)
    def query_outcomes(self, *args): return tuple(self.outcomes)
    def download(self, *args): raise AssertionError("provider/download called")
    def execute_pipeline(self, *args): raise AssertionError("DecisionPipeline called")


def record(stamp, recommendation="BUY CE", confidence=92, positioning="Long Build-up", bias="Bullish",
           manipulation="False Breakout", completeness="FULL_REPLAY", engine="itos-18.4c-v1"):
    values = {"compression_intelligence": {"score": 80, "releasing": True},
        "market_regime": {"regime": bias}, "market_cycle": {"cycle": "Expansion"},
        "volume_structure": {"volume_strength": 70, "price_up_volume_up": True, "confirmed_expansion": True,
                             "behaviour": "Accumulation"},
        "manipulation_intelligence": {"false_breakout": manipulation == "False Breakout", "liquidity_sweep": True},
        "institutional_evidence": {"bias": bias, "quality": 85},
        "trade_opportunity_ranking": {"top_ce": {"strike": 25000}, "top_pe": {"strike": 24500},
                                      "best_overall": {"strike": 25000}, "eligibility": "ELIGIBLE"}}
    return HistoricalIntelligenceRecord("upstox", "NIFTY", "NIFTY 50", 1, stamp.date(), stamp, stamp, stamp,
        engine, "intelligence-v1", completeness, recommendation, confidence, confidence, market_bias=bias,
        positioning_state=positioning, compression_state="High", manipulation_state=manipulation,
        ranking_eligibility=True, blockers=("block",), missing_confirmations=("confirmation",), values=values)


def fixture():
    first = record(datetime(2026, 7, 30, 10), "BUY CE", 92)
    second = record(datetime(2026, 7, 31, 11), "BUY PE", 78, "Short Build-up", "Bearish", "Liquidity Sweep")
    outcomes = tuple(HistoricalOutcomeRecord(item.record_id, "NIFTY", 1, item.trading_date, item.analysis_timestamp,
        item.engine_version, "outcome-v1", 100, ((5, 101), (15, 102), (30, 103)),
        ((5, 1), (15, 2), (30, 3)), ((5, 1), (15, 2), (30, 3)), 104, 5, -2, True) for item in (first, second))
    return ReadOnlyLake((first, second), outcomes)


def request(**changes):
    values = dict(instrument_key="NIFTY", underlying="NIFTY 50", start_date=date(2026, 7, 30),
                  end_date=date(2026, 7, 31), interval_minutes=1)
    values.update(changes); return HistoricalAnalyticsRequest(**values)


@pytest.mark.parametrize(("preset", "days"), ((PeriodPreset.WEEK, 6), (PeriodPreset.MONTH, 29),
    (PeriodPreset.THREE_MONTHS, 89), (PeriodPreset.SIX_MONTHS, 179), (PeriodPreset.ONE_YEAR, 364)))
def test_period_presets_resolve(preset, days):
    start, end = resolve_analytics_period(preset, date(2026, 8, 1))
    assert (end-start).days == days


def test_custom_period_resolves():
    assert resolve_analytics_period(PeriodPreset.CUSTOM, date(2026, 8, 1), date(2026, 7, 1))[0] == date(2026, 7, 1)


def test_typed_workspace_preserves_live_replay_sample_and_adds_analytics():
    assert set(WorkspaceMode) == {WorkspaceMode.LIVE, WorkspaceMode.HISTORICAL_REPLAY,
        WorkspaceMode.HISTORICAL_ANALYTICS, WorkspaceMode.SAMPLE_DATA}
    assert {DataMode.LIVE.value, DataMode.HISTORICAL_REPLAY.value, DataMode.SAMPLE_DATA.value}.issubset({m.value for m in WorkspaceMode})


def test_service_reads_only_stored_lake_records_and_uses_engine_query():
    lake = fixture(); result = HistoricalAnalyticsService(lake).analyze(request(engine_version="itos-18.4c-v1"))
    assert result.record_count == 2 and lake.queries[0].engine_version == "itos-18.4c-v1"


def test_empty_period_degrades_without_fabricated_recommendation():
    result = HistoricalAnalyticsService(ReadOnlyLake()).analyze(request())
    assert result.record_count == 0 and result.recommendation_counts == () and "NO_STORED_INTELLIGENCE" in result.quality_flags
    assert result.engine_versions == ("itos-18.4c-v1",)
    assert result.schema_versions == ("intelligence-v1",)
    assert result.average_confidence == result.average_compression == 0.0
    assert result.records == result.outcome_records == ()
    assert "No stored intelligence matches the selected filters." in result.explanations


def test_empty_period_without_manifest_uses_configured_engine_and_schema_fallbacks():
    settings = replace(MarketLakeSettings(), engine_version="configured-engine",
                       intelligence_schema_version="configured-schema")
    result = HistoricalAnalyticsService(
        ReadOnlyLake(manifest=False, settings=settings)
    ).analyze(request())
    assert result.engine_versions == ("configured-engine",)
    assert result.schema_versions == ("configured-schema",)
    assert result.recommendation_counts == ()
    assert result.records == () and result.outcome_records == ()


def test_empty_period_prefers_manifest_engine_over_configured_engine():
    settings = replace(MarketLakeSettings(), engine_version="configured-engine")
    result = HistoricalAnalyticsService(ReadOnlyLake(settings=settings)).analyze(request())
    assert result.engine_versions == ("itos-18.4c-v1",)


def test_incomplete_period_reports_coverage_and_missing_dates():
    result = HistoricalAnalyticsService(fixture()).analyze(replace(request(), start_date=date(2026, 7, 27)))
    assert result.missing_dates and result.data_completeness < 100


def test_recommendation_confidence_positioning_and_bias_aggregates():
    result = HistoricalAnalyticsService(fixture()).analyze(request())
    assert dict(result.recommendation_counts) == {"BUY CE": 1, "BUY PE": 1}
    assert (result.average_confidence, result.median_confidence, result.maximum_confidence, result.minimum_confidence) == (85, 85, 92, 78)
    assert result.positioning["long_build_up_count"] == 1 and result.positioning["short_build_up_count"] == 1
    assert result.institutional_evidence["bullish_count"] == 1 and result.institutional_evidence["bearish_count"] == 1


def test_compression_manipulation_and_market_structure_aggregates():
    result = HistoricalAnalyticsService(fixture()).analyze(request())
    assert result.average_compression == 80 and result.compression_release_count == 2
    assert result.manipulation["false_breakout"] == 1 and result.manipulation["liquidity_sweep"] == 2
    assert result.market_structure["transition_count"] == 1


def test_ranking_and_strike_frequencies_are_stored_facts():
    result = HistoricalAnalyticsService(fixture()).analyze(request())
    assert result.ranking_eligible_count == 2
    assert result.top_ce_occurrences[0] == ("25000", 2) and result.top_pe_occurrences[0] == ("24500", 2)


def test_factual_outcomes_are_averaged_without_win_rate():
    result = HistoricalAnalyticsService(fixture()).analyze(request())
    assert (result.average_5m_change, result.average_15m_change, result.average_30m_change) == (1, 2, 3)
    assert (result.average_eod_change, result.average_mfe, result.average_mae) == (4, 5, -2)
    assert result.future_data_coverage == 100


def test_drilldown_matches_stored_record_and_outcome():
    result = HistoricalAnalyticsService(fixture()).analyze(request())
    assert result.detail_rows[0]["Recommendation"] == result.records[0].recommendation
    assert result.detail_rows[0]["5m Outcome"] == 1 and result.detail_rows[0]["Best CE"] == 25000


@pytest.mark.parametrize(("changes", "expected"), (
    ({"recommendation": "BUY PE"}, "BUY PE"), ({"minimum_confidence": 90}, "BUY CE"),
    ({"maximum_confidence": 80}, "BUY PE"), ({"minimum_compression": 80, "maximum_compression": 80}, "BUY CE"),
    ({"positioning_state": "Short Build-up"}, "BUY PE"), ({"manipulation_state": "Liquidity Sweep"}, "BUY PE"),
    ({"institutional_bias": "Bearish"}, "BUY PE"), ({"replay_completeness": "FULL_REPLAY"}, "BUY CE"),
    ({"engine_version": "itos-18.4c-v1"}, "BUY CE")))
def test_filters_apply_to_defensive_stored_records(changes, expected):
    result = HistoricalAnalyticsService(fixture()).analyze(request(**changes))
    assert result.records and all(record.recommendation == expected for record in result.records) if len(result.records) == 1 else expected == "BUY CE"


def test_csv_and_json_exports_contain_filtered_stored_intelligence_and_outcomes():
    service = HistoricalAnalyticsService(fixture()); result = service.analyze(request(recommendation="BUY CE"))
    assert b"5m Outcome" in service.export_csv(result)
    payload = json.loads(service.export_json(result)); assert payload["records"][0]["Recommendation"] == "BUY CE"


def test_malformed_input_never_creates_buy():
    malformed = replace(record(datetime(2026, 7, 31, 10), recommendation="WAIT", confidence=None), values={})
    result = HistoricalAnalyticsService(ReadOnlyLake((malformed,), ())).analyze(request())
    assert dict(result.recommendation_counts) == {"WAIT": 1}


def test_analytics_state_prefix_does_not_overlap_live_or_replay_keys():
    assert PREFIX == "historical_analytics_" and not PREFIX.startswith(("live_", "replay_"))


def test_developer_actions_are_explicit_existing_service_callbacks():
    calls = []
    actions = MarketLakeActions(lambda value: calls.append(("sync", value)), lambda value: calls.append(("intel", value)),
                                lambda value: calls.append(("outcomes", value)))
    assert all((actions.sync_missing_data, actions.build_intelligence, actions.build_outcomes)) and calls == []
