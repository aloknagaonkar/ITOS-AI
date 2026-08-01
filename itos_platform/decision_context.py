from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd

@dataclass(frozen=True)
class MarketSnapshot:
    """Canonical, point-in-time market inputs shared by analysis engines."""

    option_result: Mapping[str, Any]
    intelligence: Mapping[str, Any]
    institutional: Any = None
    last_refresh: str = ""

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class DecisionContext:
    """Typed decision-layer inputs; never adds decision state to a snapshot."""

    market_snapshot: MarketSnapshot
    recommendation: Mapping[str, Any]
    cycle_result: Any | None
    confidence_history: pd.DataFrame | Any = field(default_factory=pd.DataFrame)
    phase_history: pd.DataFrame | Any = field(default_factory=pd.DataFrame)
    runtime: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "market_snapshot":
            return self.market_snapshot
        if hasattr(self, key):
            return getattr(self, key)
        snapshot_value = self.market_snapshot.get(key, default)
        if snapshot_value is not default:
            return snapshot_value
        return self.runtime.get(key, default)

    @classmethod
    def from_legacy(cls, values: Mapping[str, Any]) -> "DecisionContext":
        snapshot = values.get("market_snapshot")
        if not isinstance(snapshot, MarketSnapshot):
            snapshot = MarketSnapshot(
                option_result=values.get("option_result") or {},
                intelligence=values.get("intelligence") or {},
                institutional=values.get("institutional"),
                last_refresh=str(values.get("last_refresh") or ""),
            )
        known = {
            "market_snapshot", "option_result", "intelligence", "institutional",
            "last_refresh", "recommendation", "cycle_result", "confidence_history",
            "phase_history",
        }
        return cls(
            market_snapshot=snapshot,
            recommendation=values.get("recommendation") or {},
            cycle_result=values.get("cycle_result"),
            confidence_history=values.get("confidence_history"),
            phase_history=values.get("phase_history"),
            runtime={key: value for key, value in values.items() if key not in known},
        )
