from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EngineResult:
    """Standard response returned by every ITOS analysis engine.

    The original constructor remains compatible: existing engines can continue to
    pass ``engine, score, vote, explanation, metadata`` positionally. New fields
    are optional and provide calibrated confidence and weighting information to
    the orchestrator.
    """

    engine: str
    score: float
    vote: str
    explanation: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    weight: float = 1.0
    captured_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds")
    )

    def __post_init__(self) -> None:
        self.score = max(0.0, min(float(self.score), 100.0))
        self.vote = str(self.vote or "WAIT").upper()
        if self.confidence is None:
            self.confidence = self.score
        self.confidence = max(0.0, min(float(self.confidence), 100.0))
        self.weight = max(0.0, float(self.weight))
        self.explanation = [str(item) for item in self.explanation if str(item).strip()]
        self.metadata = dict(self.metadata or {})

    @property
    def bullish(self) -> bool:
        return self.vote in {"CE", "BUY", "BULLISH", "BUY CE"}

    @property
    def bearish(self) -> bool:
        return self.vote in {"PE", "SELL", "BEARISH", "BUY PE"}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseEngine(ABC):
    """Common interface for all pluggable intelligence engines."""

    name = "Base Engine"

    @abstractmethod
    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        raise NotImplementedError

    def score(self, result: EngineResult) -> float:
        return float(result.score)

    def explain(self, result: EngineResult) -> list[str]:
        return list(result.explanation)

    def vote(self, result: EngineResult) -> str:
        return str(result.vote)

    def save_history(self, result: EngineResult, store: Any, **context: Any) -> None:
        """Optional persistence hook. Engines may override this."""
        return None
