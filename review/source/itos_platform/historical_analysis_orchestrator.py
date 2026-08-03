"""One-click, resumable orchestration for Historical Analysis.

This module coordinates the existing Market Lake services; it deliberately owns no
market calculations and persists no credentials or runtime clients.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from .market_lake import HistoricalRangeRequest, MarketLakeSettings


class PipelineStage(str, Enum):
    PLAN = "PLAN"
    DOWNLOAD_UNDERLYING = "DOWNLOAD_UNDERLYING"
    DOWNLOAD_OPTIONS = "DOWNLOAD_OPTIONS"
    BUILD_INTELLIGENCE = "BUILD_INTELLIGENCE"
    BUILD_OUTCOMES = "BUILD_OUTCOMES"
    BUILD_INDEX = "BUILD_INDEX"
    PREPARE_ANALYTICS = "PREPARE_ANALYTICS"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class HistoricalAnalysisSettings:
    simple_ui_enabled: bool = True
    default_underlying: str = "NIFTY"
    default_interval_minutes: int = 1
    default_cadence_minutes: int = 5
    include_options_default: bool = True
    maximum_date_range_days: int = 366
    auto_build_intelligence: bool = True
    auto_build_outcomes: bool = True
    auto_build_index: bool = True
    auto_prepare_analytics: bool = True
    checkpoint_enabled: bool = True
    resume_enabled: bool = True
    cancel_after_current_date_enabled: bool = True
    retry_failed_dates_enabled: bool = True
    missed_opportunity_summary_enabled: bool = True
    normal_ui_json_disabled: bool = True
    advanced_controls_enabled: bool = True


@dataclass(frozen=True)
class HistoricalAnalysisRunRequest:
    underlying: str
    instrument_key: str
    start_date: date
    end_date: date
    interval_minutes: int = 1
    analysis_cadence_minutes: int = 5
    include_historical_options: bool = True
    download_missing_only: bool = True
    rebuild_intelligence: bool = False
    rebuild_outcomes: bool = False
    rebuild_index: bool = False
    requested_at: datetime | None = None

    def validate(self, settings: HistoricalAnalysisSettings, supported: Mapping[str, str], *, today=None):
        if self.underlying not in supported or supported[self.underlying] != self.instrument_key:
            raise ValueError("The selected instrument is not supported.")
        HistoricalRangeRequest(self.underlying, self.instrument_key, self.start_date,
            self.end_date, self.interval_minutes).validate(MarketLakeSettings(
                maximum_sync_range=settings.maximum_date_range_days), today=today)

    def range_request(self) -> HistoricalRangeRequest:
        return HistoricalRangeRequest(self.underlying, self.instrument_key, self.start_date,
            self.end_date, self.interval_minutes, include_options=self.include_historical_options,
            rebuild_raw=not self.download_missing_only,
            rebuild_intelligence=self.rebuild_intelligence, rebuild_outcomes=self.rebuild_outcomes)


@dataclass(frozen=True)
class DatePipelineStatus:
    trading_date: date
    session: str = "EXPECTED_WEEKDAY"
    underlying: str = "Pending"
    options: str = "Pending"
    intelligence: str = "Pending"
    outcomes: str = "Pending"
    index: str = "Not indexed"
    final: str = "Pending"
    explanation: str = "Waiting"


@dataclass(frozen=True)
class HistoricalPipelineProgress:
    run_id: str
    overall_status: str
    stage: str
    stage_status: str
    overall_percent: float
    stage_percent: float
    current_date: date | None
    status_message: str
    expected_dates: int
    underlying_total: int = 0
    underlying_complete: int = 0
    option_total: int = 0
    option_complete: int = 0
    option_partial: int = 0
    intelligence_total: int = 0
    intelligence_complete: int = 0
    outcome_total: int = 0
    outcome_complete: int = 0
    index_total: int = 0
    index_complete: int = 0
    completed_dates: tuple[date, ...] = ()
    partial_dates: tuple[date, ...] = ()
    failed_dates: tuple[date, ...] = ()
    skipped_dates: tuple[date, ...] = ()
    date_statuses: tuple[DatePipelineStatus, ...] = ()
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "overall_percent", min(100.0, max(0.0, self.overall_percent)))
        object.__setattr__(self, "stage_percent", min(100.0, max(0.0, self.stage_percent)))


@dataclass(frozen=True)
class HistoricalAnalysisRunResult:
    run_id: str
    status: str
    progress: HistoricalPipelineProgress
    analytics: Any = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class HistoricalAnalysisRunState:
    run_id: str
    request: HistoricalAnalysisRunRequest
    stage: str
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    current_date: date | None = None
    cancel_requested: bool = False
    completed_dates: tuple[date, ...] = ()
    partial_dates: tuple[date, ...] = ()
    failed_dates: tuple[date, ...] = ()
    skipped_dates: tuple[date, ...] = ()
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


class JsonRunCheckpointStore:
    """Atomic, token-free checkpoint documents, recoverable after restart."""
    def __init__(self, root: str | Path): self.root = Path(root)
    def save(self, request: HistoricalAnalysisRunRequest, progress: HistoricalPipelineProgress):
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"request": asdict(request), "progress": asdict(progress)}
        payload = json.loads(json.dumps(payload, default=lambda value: value.isoformat()))
        temporary = self.root / f".{progress.run_id}.tmp"
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(self.root / f"{progress.run_id}.json")


class HistoricalAnalysisOrchestrator:
    """Sequential failure-isolated coordinator around existing service callbacks."""
    STAGES = tuple(PipelineStage)

    def __init__(self, *, sync_underlying, download_options=None, build_intelligence=None,
                 build_outcomes=None, build_index=None, prepare_analytics=None,
                 checkpoint_store=None, settings=HistoricalAnalysisSettings()):
        self.operations = {PipelineStage.DOWNLOAD_UNDERLYING: sync_underlying,
            PipelineStage.DOWNLOAD_OPTIONS: download_options,
            PipelineStage.BUILD_INTELLIGENCE: build_intelligence,
            PipelineStage.BUILD_OUTCOMES: build_outcomes,
            PipelineStage.BUILD_INDEX: build_index,
            PipelineStage.PREPARE_ANALYTICS: prepare_analytics}
        self.checkpoints, self.settings = checkpoint_store, settings
        self.cancel_requested = False

    def cancel_after_current_date(self): self.cancel_requested = True

    def run(self, request, *, progress_callback=None, run_id=None):
        run_id, started = run_id or uuid4().hex, datetime.now(timezone.utc)
        dates = tuple(request.start_date.fromordinal(n) for n in range(
            request.start_date.toordinal(), request.end_date.toordinal() + 1))
        rows = tuple(DatePipelineStatus(d, "NOT_TRADING_SESSION", final="Skipped", explanation="Weekend")
            if d.weekday() >= 5 else DatePipelineStatus(d) for d in dates)
        active = tuple(r.trading_date for r in rows if r.session != "NOT_TRADING_SESSION")
        previous = 0.0
        analytics = None
        def emit(stage, status, message, percent, current=None, failed=(), partial=()):
            nonlocal previous
            previous = max(previous, percent)
            done = len(active) if status in ("COMPLETE", "PARTIAL") else 0
            progress = HistoricalPipelineProgress(run_id, status, stage.value, status, previous, 100.0,
                current, message, len(dates), len(active), done,
                len(active) if request.include_historical_options else 0,
                done if stage.value >= PipelineStage.DOWNLOAD_OPTIONS.value else 0, len(partial),
                len(active), done if stage.value >= PipelineStage.BUILD_INTELLIGENCE.value else 0,
                len(active), done if stage.value >= PipelineStage.BUILD_OUTCOMES.value else 0,
                len(active), done if stage.value >= PipelineStage.BUILD_INDEX.value else 0,
                tuple(d for d in active if d not in failed), tuple(partial),
                tuple(failed), tuple(r.trading_date for r in rows if r.final == "Skipped"), rows)
            if self.checkpoints and self.settings.checkpoint_enabled: self.checkpoints.save(request, progress)
            if progress_callback: progress_callback(progress)
            return progress
        progress = emit(PipelineStage.PLAN, "COMPLETE", f"Prepared {len(dates)} requested dates.", 12.5)
        failed, partial = set(), set()
        for number, stage in enumerate(self.STAGES[1:-1], 1):
            operation = self.operations.get(stage)
            if operation is None or (stage is PipelineStage.DOWNLOAD_OPTIONS and not request.include_historical_options):
                progress = emit(stage, "SKIPPED", "Stage is unavailable or disabled.", (number+1)*12.5,
                                failed=failed, partial=partial); continue
            if self.cancel_requested:
                return HistoricalAnalysisRunResult(run_id, "CANCELLED",
                    emit(stage, "CANCELLED", "Cancelled safely; completed work was preserved.", previous,
                         failed=failed, partial=partial), started_at=started)
            try:
                value = operation(request.range_request())
                if stage is PipelineStage.PREPARE_ANALYTICS: analytics = value
                message = stage.value.replace("_", " ").title() + " complete."
                progress = emit(stage, "COMPLETE", message, (number+1)*12.5,
                                active[-1] if active else None, failed, partial)
            except Exception as error:
                # Options are explicitly non-blocking; all failures preserve prior stages.
                message = str(error).strip() or "The stage could not be completed."
                if stage is PipelineStage.DOWNLOAD_OPTIONS:
                    partial.update(active); progress = emit(stage, "PARTIAL", message, (number+1)*12.5,
                        failed=failed, partial=partial); continue
                failed.update(active); progress = emit(stage, "FAILED", message, (number+1)*12.5,
                    failed=failed, partial=partial)
                if stage is PipelineStage.BUILD_INDEX: continue
        status = "PARTIAL" if failed or partial else "COMPLETE"
        progress = emit(PipelineStage.COMPLETE, status, "Results ready." if analytics is not None else
            "Processing finished; no qualifying historical setups were found.", 100.0, failed=failed, partial=partial)
        return HistoricalAnalysisRunResult(run_id, status, progress, analytics, started, datetime.now(timezone.utc))
