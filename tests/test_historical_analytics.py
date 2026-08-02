from datetime import date, datetime

from itos_platform.historical_analytics import AnalyticsFilters, HistoricalAnalyticsService
from itos_platform.market_lake import (
    DatasetManifest, HistoricalIntelligenceRecord, HistoricalOutcomeRecord, MarketLakeSettings,
)


class ReadOnlyLake:
    settings = MarketLakeSettings()

    def __init__(self):
        self.queries = []
        stamp = datetime(2026, 7, 31, 10)
        self.records = (HistoricalIntelligenceRecord("upstox", "NIFTY", "NIFTY 50", 1, date(2026, 7, 31),
            stamp, stamp, stamp, self.settings.engine_version, self.settings.intelligence_schema_version,
            "FULL_REPLAY", "BUY CE", 88, 88, market_bias="Bullish", positioning_state="Long Build-up",
            compression_state="High", ranking_eligibility=True,
            values={"compression": {"score": 75, "release": True}, "market_regime": {"regime": "Bullish"},
                    "market_cycle": {"cycle": "Expansion"}, "trade_opportunity_ranking": {"top_ce": {"strike": 25000}}}),)
        self.outcomes = (HistoricalOutcomeRecord(self.records[0].record_id, "NIFTY", 1, date(2026, 7, 31), stamp,
            self.settings.engine_version, self.settings.outcome_schema_version, 100, ((5, 101), (15, 102), (30, 99)),
            ((5, 1), (15, 2), (30, -1)), ((5, 1), (15, 2), (30, -1)), 103, 4, -2, True),)

    def get_manifest(self, provider, instrument, interval):
        return DatasetManifest("id", provider, instrument, "NIFTY 50", interval, 5,
            engine_version=self.settings.engine_version, available_dates=(date(2026, 7, 31),),
            intelligence_dates=(date(2026, 7, 31),), option_dates=(date(2026, 7, 31),))

    def query_intelligence(self, query):
        self.queries.append(query)
        return tuple(r for r in self.records if query.recommendation in (None, r.recommendation))

    def query_outcomes(self, *args): return self.outcomes

    def download(self, *args): raise AssertionError("analytics must not download")
    def execute_pipeline(self, *args): raise AssertionError("analytics must not run the decision pipeline")


def test_period_aggregation_populates_existing_card_groups_without_acquisition():
    lake = ReadOnlyLake()
    result = HistoricalAnalyticsService(lake).analyze(underlying="NIFTY 50", instrument_key="NIFTY",
                                                       period="Week", end_date=date(2026, 7, 31))
    assert result.header.analysis_points == 1
    assert result.cards["trade_opportunity_ranking"]["buy_ce"] == 1
    assert result.cards["historical_outcomes"]["5_minutes"] == 1
    assert lake.queries[0].start_date == date(2026, 7, 25)


def test_custom_range_filters_drilldown_and_exports_use_stored_records():
    lake = ReadOnlyLake(); service = HistoricalAnalyticsService(lake)
    result = service.analyze(underlying="NIFTY 50", instrument_key="NIFTY", period="Custom Range",
        start_date=date(2026, 7, 31), end_date=date(2026, 7, 31),
        filters=AnalyticsFilters(recommendation="BUY CE", minimum_confidence=80, search="10:00"))
    assert result.detail_rows[0]["Top CE"] == 25000
    assert b"Recommendation" in service.export_csv(result)
    assert lake.queries[0].minimum_confidence == 80


def test_incomplete_period_reports_missing_dates_instead_of_syncing():
    result = HistoricalAnalyticsService(ReadOnlyLake()).analyze(underlying="NIFTY 50", instrument_key="NIFTY",
                                                                period="Week", end_date=date(2026, 7, 31))
    assert result.header.market_lake_status == "INCOMPLETE"
    assert result.header.missing_dates
