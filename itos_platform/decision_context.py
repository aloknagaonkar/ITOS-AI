"""Immutable inputs shared by the ITOS 2.0 decision pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any


def recommendation_is_available(recommendation: Any) -> bool:
    """Return whether a recommendation has the minimum decision identity."""

    return isinstance(recommendation, Mapping) and all(
        key in recommendation for key in ("side", "status")
    )


@dataclass(frozen=True)
class MarketSnapshot:
    """A point-in-time view of all market data used for a decision.

    The containers are deliberately left in their provider-native forms during
    the migration (for example, candle data remains a pandas DataFrame).  The
    frozen boundary prevents pipeline stages from replacing any part of the
    snapshot while preserving compatibility with today's analysis functions.
    """

    option_result: Mapping[str, Any]
    intelligence: Mapping[str, Any]
    historical_candles: Any = None
    timestamps: Mapping[str, Any] = field(default_factory=dict)
    selected_instrument: str = ""
    expiry: str = ""
    timeframe: int | str | None = None
    data_quality: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legacy(cls, market_data: Mapping[str, Any]) -> "MarketSnapshot":
        """Adapt the dictionary contract used by pre-2.0 callers."""

        timestamps = dict(market_data.get("timestamps") or {})
        if "last_refresh" in market_data:
            timestamps.setdefault("last_refresh", market_data.get("last_refresh"))

        data_quality = dict(market_data.get("data_quality") or {})
        if "recommendation" in market_data:
            data_quality.setdefault(
                "recommendation_available",
                recommendation_is_available(market_data.get("recommendation")),
            )

        return cls(
            option_result=market_data.get("option_result") or {},
            intelligence=market_data.get("intelligence") or {},
            historical_candles=market_data.get(
                "historical_pattern_candles", market_data.get("historical_candles")
            ),
            timestamps=timestamps,
            selected_instrument=str(
                market_data.get("selected_instrument")
                or market_data.get("instrument_key")
                or market_data.get("underlying")
                or ""
            ),
            expiry=str(market_data.get("expiry") or ""),
            timeframe=market_data.get("timeframe"),
            data_quality=data_quality,
        )


@dataclass(frozen=True)
class DecisionContext:
    """Runtime dependencies and state accompanying a market snapshot."""

    market_snapshot: MarketSnapshot
    historical_repositories: Mapping[str, Any] = field(default_factory=dict)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    session_state: Mapping[str, Any] = field(default_factory=dict)
    runtime_settings: Mapping[str, Any] = field(default_factory=dict)
