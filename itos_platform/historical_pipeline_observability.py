"""Structured, secret-safe observability for Historical Analysis runs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
import logging
from pathlib import Path
import re
import time
from typing import Any, Mapping
from uuid import uuid4

LOGGER_NAME = "historical_pipeline"
_SECRET = re.compile(r"(?i)(authorization|oauth|access[_ -]?token|broker[_ -]?secret)(\s*[=:]\s*)(\S+)")


def generate_run_id() -> str:
    """Return a short stable identifier suitable for UI and file names."""
    return uuid4().hex[:6].upper()


def _safe(value: Any) -> str:
    return _SECRET.sub(r"\1\2[REDACTED]", str(value).replace("\n", " "))


@dataclass
class PipelineDiagnostics:
    run_id: str
    current_stage: str = "PLAN"
    last_completed_stage: str = "—"
    current_date: date | None = None
    last_successful_date: date | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_progress: float = 0.0
    completed_dates: tuple[date, ...] = ()
    failed_dates: tuple[date, ...] = ()
    skipped_dates: tuple[date, ...] = ()
    partial_dates: tuple[date, ...] = ()
    last_exception: str = "—"
    stage_durations: dict[str, float] = field(default_factory=dict)
    checkpoint_path: str = "—"
    resume_available: bool = False

    @property
    def elapsed_time(self) -> float:
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()


class HistoricalPipelineObserver:
    """Owns one run's logger, timings, and read-only diagnostic state."""
    def __init__(self, run_id: str, *, log_root: str | Path = "logs/historical",
                 checkpoint_path: str | Path | None = None, stall_threshold_seconds: float = 60.0):
        self.run_id = run_id
        self.stall_threshold_seconds = stall_threshold_seconds
        folder = Path(log_root) / datetime.now(timezone.utc).date().isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        self.log_path = folder / f"run_{run_id}.log"
        self.diagnostics = PipelineDiagnostics(run_id, checkpoint_path=str(checkpoint_path or "—"))
        self._starts: dict[str, float] = {}
        self.logger = logging.getLogger(f"{LOGGER_NAME}.{run_id}")
        self.logger.setLevel(logging.INFO); self.logger.propagate = True
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [RUN:%(run_id)s] %(levelname)s %(message)s"))
        handler.addFilter(_RunFilter(run_id))
        self.logger.addHandler(handler)
        self._handler = handler

    def log(self, message: str, **fields: Any) -> None:
        suffix = " ".join(f"{key}={'[REDACTED]' if _SECRET.search(key + '=x') else _safe(value)}"
            for key, value in fields.items() if value is not None)
        self.logger.info("%s%s", _safe(message), f" {suffix}" if suffix else "")

    def stage_started(self, stage: str, affected_dates=()) -> None:
        self._starts[stage] = time.monotonic(); self.diagnostics.current_stage = stage
        self.log(f"{stage} started", affected_dates=",".join(map(str, affected_dates)))

    def stage_completed(self, stage: str, affected_dates=()) -> float:
        duration = time.monotonic() - self._starts.pop(stage, time.monotonic())
        self.diagnostics.stage_durations[stage] = duration
        self.diagnostics.last_completed_stage = stage
        self.log(f"{stage} completed", duration_seconds=f"{duration:.3f}", affected_dates=",".join(map(str, affected_dates)))
        return duration

    def stage_failed(self, stage: str, error: BaseException, *, day: date | None = None) -> None:
        duration = time.monotonic() - self._starts.get(stage, time.monotonic())
        self.diagnostics.stage_durations[stage] = duration
        self.diagnostics.last_exception = f"{type(error).__name__}: {_safe(error)}"
        # Do not attach a traceback: exception source lines and locals can contain
        # OAuth credentials even when the formatted exception has been redacted.
        self.logger.error("%s failed stage=%s date=%s duration_seconds=%.3f exception_type=%s message=%s",
            stage, stage, day, duration, type(error).__name__, _safe(error))

    def date_status(self, day: date, stage: str, status: str, **metrics: Any) -> None:
        self.diagnostics.current_date = day
        self.log("date status", date=day, stage=stage, status=status, **metrics)

    def validate_stall(self, stage: str, day: date | None, elapsed: float, last_operation: str) -> bool:
        if elapsed <= self.stall_threshold_seconds: return False
        self.log("Possible stalled stage", current_stage=stage, current_date=day,
                 elapsed_seconds=f"{elapsed:.3f}", last_completed_operation=last_operation)
        return True

    def close(self) -> None:
        self._handler.flush(); self._handler.close(); self.logger.removeHandler(self._handler)


class _RunFilter(logging.Filter):
    def __init__(self, run_id: str): super().__init__(); self.run_id = run_id
    def filter(self, record): record.run_id = self.run_id; return True


def normalize_dataframe_value(value: Any) -> Any:
    """Convert values unsupported by Arrow to deterministic readable primitives."""
    if value is None or isinstance(value, (str, int, float, bool, date, datetime)): return value
    if is_dataclass(value) and not isinstance(value, type): return _safe(asdict(value))
    if isinstance(value, Mapping): return _safe(dict(value))
    if isinstance(value, (list, tuple, set, frozenset)): return ", ".join(_safe(item) for item in value)
    return _safe(value)


def normalize_dataframe(frame):
    """Return a copy whose cells contain only Arrow-friendly values."""
    return frame.map(normalize_dataframe_value) if hasattr(frame, "map") else frame.applymap(normalize_dataframe_value)
