"""Immutable inputs shared by the ITOS 2.0 decision pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .institutional_metrics import InstitutionalMetrics


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
    recommendation: Mapping[str, Any] = field(default_factory=dict)
    engine_results: Mapping[str, Any] = field(default_factory=dict)
    cycle_result: Any = None
    confidence_history: Any = None
    phase_history: Any = None
    runtime_configuration: Mapping[str, Any] = field(default_factory=dict)
    runtime: Mapping[str, Any] = field(default_factory=dict)
    historical_repositories: Mapping[str, Any] = field(default_factory=dict)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    session_state: Mapping[str, Any] = field(default_factory=dict)
    runtime_settings: Mapping[str, Any] = field(default_factory=dict)
    institutional: Mapping[str, Any] | None = None
    institutional_metrics: InstitutionalMetrics | None = None
    decision_history: Any = None
    strike_history: Any = None
    stability_history: Any = None
    flow_result: Any = None
    institutional_confidence_result: Any = None
    validation_result: Any = None
    confirmation_result: Any = None
    stability_result: Any = None
    false_breakout_result: Any = None

    def __post_init__(self) -> None:
        """Reconcile canonical fields with Sprint 2 constructor aliases."""

        engine_results = dict(self.engine_results or {})
        cycle_result = self.cycle_result
        if cycle_result is None:
            cycle_result = engine_results.get("market_cycle")
        elif "market_cycle" not in engine_results:
            engine_results["market_cycle"] = cycle_result

        result_fields = {
            "flow_result": "institutional_flow",
            "institutional_confidence_result": "institutional_confidence",
            "validation_result": "signal_validation",
            "confirmation_result": "institutional_confirmation",
            "stability_result": "recommendation_stability",
            "false_breakout_result": "false_breakout",
        }
        for field_name, result_name in result_fields.items():
            value = getattr(self, field_name)
            if value is None:
                object.__setattr__(self, field_name, engine_results.get(result_name))
            elif result_name not in engine_results:
                engine_results[result_name] = value

        runtime_configuration = dict(self.runtime or {})
        runtime_configuration.update(self.runtime_configuration or {})
        object.__setattr__(self, "engine_results", engine_results)
        object.__setattr__(self, "cycle_result", cycle_result)
        object.__setattr__(self, "runtime_configuration", runtime_configuration)
        object.__setattr__(self, "runtime", runtime_configuration)
