"""Application composition for the explicit historical workflow.

Objects in this module are ordinary process-scoped dependencies.  In particular,
no database connection or authenticated client is placed in Streamlit state.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dashboard_application_service import DashboardApplicationService

from .historical_intelligence_index import (
    HistoricalIndexSettings, HistoricalIntelligenceIndexService,
    SQLiteHistoricalIntelligenceIndex,
)
from .historical_options import HistoricalOptionDownloadService
from .historical_similarity import HistoricalSimilarityService
from .historical_sync import HistoricalSyncManager, UpstoxHistoricalSyncProvider
from .live_market_lake import AfterMarketFinalizationService, LiveMarketLakeCaptureService
from .market_lake import IntelligenceQuery, LocalHistoricalMarketLake, MarketLakeSettings
from .replay import DataMode, HistoricalReplayProvider, ReplayRequest


class HistoricalPointInTimeRunner:
    """Run the existing dashboard pipeline once against Market Lake data only."""

    def __init__(self, lake: LocalHistoricalMarketLake, *, provider: str = "upstox",
                 application_factory: Callable[..., DashboardApplicationService] = DashboardApplicationService):
        self.lake = lake
        self.provider_name = provider
        self.replay_provider = HistoricalReplayProvider(
            lambda request: lake.load_raw_candles(
                provider, request.instrument_key, request.interval_minutes,
                request.trading_date,
            ),
            candle_source="market_lake",
        )
        self.application_factory = application_factory

    def __call__(self, request: ReplayRequest) -> Any:
        # A fresh dictionary prevents Live/replay UI state from becoming fallback data.
        application = self.application_factory(provider=self.replay_provider)
        return application.execute(
            token="", instrument_key=request.instrument_key,
            underlying=request.underlying, expiry=str(request.expiry or ""),
            timeframe=request.interval_minutes, strikes=0, save_snapshots=False,
            history_hours=0, should_load=False, session_state={},
            data_mode=DataMode.HISTORICAL_REPLAY, replay_request=request,
        )


@dataclass(frozen=True)
class HistoricalPipelineComposition:
    lake: LocalHistoricalMarketLake
    index: SQLiteHistoricalIntelligenceIndex
    sync_manager: HistoricalSyncManager
    runner: HistoricalPointInTimeRunner
    index_service: HistoricalIntelligenceIndexService
    similarity_service: HistoricalSimilarityService
    option_service: HistoricalOptionDownloadService | None
    live_capture: LiveMarketLakeCaptureService
    finalization: AfterMarketFinalizationService

    def intelligence_records(self, request):
        return self.lake.query_intelligence(IntelligenceQuery(
            request.instrument_key, request.start_date, request.end_date,
            request.interval_minutes, engine_version=self.lake.settings.engine_version,
        ))

    def intelligence_artifact_current(self, request, *, cadence_minutes=5):
        return self.lake.intelligence_artifact_current(
            self.runner.provider_name, request.instrument_key,
            request.interval_minutes, request.start_date,
            cadence_minutes=cadence_minutes,
        )

    def build_intelligence(self, request, *, cadence_minutes=5):
        return self.sync_manager.build_intelligence(
            request, runner=self.runner, cadence_minutes=cadence_minutes,
        )

    def outcome_artifact_current(self, request):
        return self.lake.outcome_artifact_current(
            request.instrument_key, request.interval_minutes, request.start_date
        )

    def build_outcomes(self, request):
        return self.sync_manager.build_outcomes(request)

    def build_index(self, request, *, rebuild_outdated=False, full_rebuild=False):
        return self.index_service.build(
            self.intelligence_records(request), rebuild_outdated=rebuild_outdated,
            full_rebuild=full_rebuild,
        )

    def validate_index(self, request):
        return self.index.validate_index(self.intelligence_records(request))


def compose_historical_pipeline(client: Any | None = None, *, root: str | Path = "data/market_lake",
                                index_path: str | Path | None = None) -> HistoricalPipelineComposition:
    """Create exactly one lake and index and inject them into every service."""
    root = Path(root)
    lake = LocalHistoricalMarketLake(MarketLakeSettings(market_lake_root=root))
    settings = HistoricalIndexSettings(
        historical_index_path=Path(index_path) if index_path else root / "index" / "historical_intelligence.sqlite"
    )
    index = SQLiteHistoricalIntelligenceIndex(settings)
    index_service = HistoricalIntelligenceIndexService(index, settings)
    provider = UpstoxHistoricalSyncProvider(client=client) if client is not None else None
    manager = HistoricalSyncManager(provider=provider, market_lake=lake)
    runner = HistoricalPointInTimeRunner(lake)
    return HistoricalPipelineComposition(
        lake, index, manager, runner, index_service,
        HistoricalSimilarityService(index),
        HistoricalOptionDownloadService(client, lake) if client is not None else None,
        LiveMarketLakeCaptureService(lake), AfterMarketFinalizationService(lake),
    )
