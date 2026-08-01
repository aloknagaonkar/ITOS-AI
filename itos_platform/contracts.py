from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    connected: bool
    latency_ms: float | None = None
    last_success_at: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketDataEnvelope:
    provider: str
    data_type: str
    payload: Any
    captured_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds")
    )
    source_timestamp: str | None = None
    quality_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DataProvider(ABC):
    """Broker/data-source neutral contract for the ITOS Data Layer."""

    name = "Data Provider"

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def get_market_data(self, request: dict[str, Any]) -> MarketDataEnvelope:
        raise NotImplementedError
