# Changelog

## Unreleased — Resilient Upstox Candle Acquisition
- Prefer the Upstox V3 intraday candle endpoint with exactly-once instrument-key encoding.
- Fall back to the latest trading day returned by the V3 historical candle endpoint.
- Normalize empty, missing, malformed, and non-200 candle responses without exposing tokens in logs.
- Block trading, force WAIT, and warn the dashboard when all candle sources are unavailable.
- Add acquisition and downstream safety regression coverage.


## Sprint 7 - Market State & Early Warning Migration

- Migrated Market Regime, Smart Money Index, Market Energy, and Early Warning engines to prefer the canonical `DecisionContext` while retaining legacy mapping inputs.
- Wired the dashboard's single decision context through all four engines without changing their execution order.
- Added typed/legacy parity, malformed-input degradation, cached pipeline characterization, and blocked-recommendation safety coverage.

## Unreleased
- Migrated the institutional radar, flow, confidence, and decision-matrix engines to prefer the canonical `DecisionContext` while retaining legacy mapping compatibility and unchanged scoring behavior.
- Extended dashboard orchestration to reuse one decision context across all four institutional engines and to carry decision/strike histories outside `MarketSnapshot`.
- Added typed-versus-legacy parity, safe-degradation, and dashboard context-identity characterization coverage for the Sprint 6 migration.
- Migrated `PhaseTransitionEngine` to prefer `DecisionContext`, preserving its legacy mapping adapter and unchanged transition calculations.
- Updated dashboard orchestration so phase-transition and recommendation-stability analysis share the canonical decision context.
- Migrated `RecommendationStabilityEngine` to prefer `DecisionContext` while retaining parity-preserving legacy dictionary input.
- Extended `DecisionContext` with explicit recommendation, engine-result, confidence-history, phase-history, and runtime-configuration fields without adding decision state to `MarketSnapshot`.
- Updated dashboard orchestration to pass its single context to recommendation stability and its single snapshot to market-cycle and data-health analysis.
- Migrated `MarketCycleEngine` to use the canonical typed `MarketSnapshot` input while preserving a legacy dictionary adapter and unchanged cycle decisions.
- Updated the dashboard application pipeline so market-cycle and data-health analysis share the same snapshot instance.

## 9.2.1
- Added weighted institutional confidence analysis.
- Added smart strike ranking.
- Added a fault-tolerant AI orchestrator.
- Extended EngineResult with confidence and weight metadata.
- Added v9.2.1 smoke tests and release notes.

## 8.4.0

- Added two primary Streamlit tabs: Live Market Intelligence and Intelligence Explorer.
- Reorganized existing information without redesigning the v8.3 interface.
- Added a sidebar version banner.
- Updated page and application version labels to v8.4.0.
- Preserved all existing engines and business logic.

## 8.4.1

- Added modular AI Trade Opportunity decision center below Key Market Levels.
- Added trade dataclasses, Explainable AI engine, AI Trade orchestrator and reusable UI renderer.
- Preserved existing engine logic and detailed dashboard panels.
# Sprint 3 - Typed Recommendation Stability Context

- Added canonical point-in-time `MarketSnapshot` and decision-layer `DecisionContext` contracts.
- Migrated `RecommendationStabilityEngine` to prefer `DecisionContext` while retaining legacy dictionary input through a boundary adapter.
- Updated dashboard orchestration to reuse one snapshot for market-cycle and data-health analysis and one context for recommendation stability.
- Added typed/legacy parity and application-service identity characterization tests.

# Sprint 5 - Structure Intelligence Migration

- Migrated Pattern Recognition, Candle DNA, Smart Candlestick, Institutional Structure, and False Breakout engines to prefer `DecisionContext` while retaining legacy dictionary calls.
- Reused the dashboard's canonical `MarketSnapshot` and `DecisionContext` across the migrated structure-intelligence pipeline without changing engine order or safety gates.
- Added typed-versus-legacy parity coverage, malformed/missing-data degradation checks, context identity characterization, and false-breakout safety parity.
