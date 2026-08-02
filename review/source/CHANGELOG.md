# Changelog

## Sprint 14 - Compression Intelligence v1

- Added an immutable, direction-neutral compression model covering ATR, rolling range, candle spread, volume, return volatility, time in range, and optional OI build-up.
- Added distinct compression, energy-stored, and expansion-readiness scores plus cautious release/expansion states, evidence, contradictions, explanations, and quality flags.
- Reused one informational-only result across DecisionContext, DecisionPipeline, PipelineResults, DashboardApplicationResult, Market Status, and the additive Compression Intelligence panel without changing recommendations or safety.
- Added behavioural contracts, formula/configuration documentation, and the Sprint 14 modified-source review package.

## Sprint 13 - Positioning Intelligence v1

- Added immutable, explainable futures-style and options positioning classifications with evidence, contradictions, confidence, quality flags, and conservative safe degradation.
- Reused one informational-only result across DecisionContext, DecisionPipeline, PipelineResults, DashboardApplicationResult, Market Status, and the additive Positioning Intelligence panel.
- Added behavioural contracts, documented configuration and formulas, and created the Sprint 13 modified-source review package without changing recommendations, safety, confidence, strikes, or planning.

## Sprint 10 - Institutional Metrics Adoption

- Adopted the shared typed InstitutionalMetrics instance across Institutional Radar, Flow, Confidence, and Decision Matrix while retaining legacy mapping adapters.
- Preserved existing formulas, thresholds, weights, decisions, execution order, and safety behavior, with quality-aware fallbacks for missing evidence.
- Added parity and shared-instance characterization plus the Sprint 10 review and modified-source packages.

## Sprint 9 - Institutional Metrics v2 Foundation

- Added immutable institutional metrics contracts, centralized option-chain normalization, and decision-neutral calculations for OI, PCR, Max Pain, volatility, Greeks, liquidity, and positioning.
- Integrated one shared metrics instance into DecisionContext, PipelineResults, and dashboard application results without changing recommendations or safety behavior.
- Added behavioural fixtures and the Sprint 9 review package; pytest remains reserved for local validation.

## Sprint 8 - Decision Pipeline & Safety Gate Foundation

- Introduced a repository-free `DecisionPipeline` that preserves the characterized engine order and shared `DecisionContext`.
- Added the frozen, named `PipelineResults` output contract and an application-layer compatibility mapping for existing dashboard field names.
- Centralized the existing cycle, stability, false-breakout, confirmation, validation, and data-health veto enforcement in a monotonic `SafetyGatePolicy`.
- Updated `DashboardApplicationService` to delegate engine orchestration while retaining acquisition, persistence, AI trade packaging, and its existing result contract.
- Added behavioural parity, context identity, cached execution, failure-safety, safety monotonicity, and dashboard smoke-contract coverage.

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
## Sprint 11 — Market Location & Transition Engine v1

- Added immutable market-location intelligence with configuration-driven zones,
  deterministic range selection, transition detection, quality flags, and safe
  degradation.
- Exposed the same informational result through the decision context, pipeline,
  application compatibility mapping, and a collapsed dashboard preview without
  changing CE, PE, or WAIT recommendation logic.
- Added deterministic behavioral coverage and a Sprint 11 review/source package.

## Sprint 12 — Volume Structure & Price-Volume Behaviour v1

- Added immutable, configuration-driven price-volume facts and location-aware interpretations with safe degradation.
- Reused one informational `VolumeStructure` through the decision context, pipeline results, compatibility mapping, and dashboard.
- Added Market Status and Price & Volume Behaviour displays without changing recommendation, confidence, safety, planning, or execution logic.
- Hardened Sprint 12 OHLC envelope validation, configurable confirmation evidence, exhaustion-window scoring, and unavailable dashboard presentation.
