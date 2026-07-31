from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TradeCandidate:
    contract: str
    option_type: str
    strike: float
    score: float
    confidence: float
    state: str
    premium: float = 0.0
    entry_trigger: float = 0.0
    stop_loss: float = 0.0
    target1: float = 0.0
    target2: float = 0.0
    delta: float = 0.0
    spread_pct: float = 0.0
    volume: float = 0.0
    oi: float = 0.0


@dataclass(frozen=True)
class ExecutionPlan:
    action: str = "WAIT"
    entry_low: float = 0.0
    entry_high: float = 0.0
    stop_loss: float = 0.0
    targets: tuple[float, ...] = ()
    risk_reward: float = 0.0
    state: str = "WAITING"
    lots: int = 0
    quantity: int = 0


@dataclass(frozen=True)
class AITradeOpportunity:
    contract: str = "No qualified contract"
    option_type: str = "WAIT"
    recommendation: str = "WAIT"
    ai_score: float = 0.0
    confidence: float = 0.0
    directional_confidence: float = 0.0
    trade_readiness: float = 0.0
    ce_strength: float = 0.0
    pe_strength: float = 0.0
    strength_advantage: float = 0.0
    recommended_side: str = "WAIT"
    early_move_side: str = "WAIT"
    early_move_probability: float = 0.0
    early_move_state: str = "NO EARLY EDGE"
    institutional_score: float = 0.0
    institutional_bias: str = "NEUTRAL"
    market_regime: str = "UNKNOWN"
    trade_quality: float = 0.0
    execution: ExecutionPlan = field(default_factory=ExecutionPlan)
    reasons: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    top_ce: tuple[TradeCandidate, ...] = ()
    top_pe: tuple[TradeCandidate, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
