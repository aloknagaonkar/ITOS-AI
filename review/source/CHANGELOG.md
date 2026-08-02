# Changelog

## Sprint 17A - Decision Confidence Engine v1

- Added immutable Decision Confidence and seven pillar contracts with configuration-driven weights, penalties, ceilings, blockers, grades, setup quality, and ranking readiness.
- Reused one shadow-only result through DecisionContext, DecisionPipeline, PipelineResults, DashboardApplicationResult, Market Status, and an additive dashboard panel.
- Added deterministic behavioural coverage, rules documentation, roadmap status, and a modified-source review package without changing recommendations, live confidence, safety, strikes, or trade planning.

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

## Sprint 15 — Manipulation Intelligence v1
- Added immutable, explainable manipulation intelligence covering failed acceptance, liquidity sweeps, stop-hunt evidence, trap risks, wick/rejection, breakout quality, follow-through quality, probability, and severity.
- Integrated one shared informational result through DecisionContext, DecisionPipeline, PipelineResults, DashboardApplicationResult, Market Status, and a new additive dashboard panel.
- Added conservative configuration, safe degradation, behavioural coverage, and the Sprint 15 review package. Recommendations, confidence, safety gates, strike selection, and trade planning are unchanged.

## Sprint 16 — Institutional Evidence Engine v1
- Added an immutable, deterministic institutional evidence aggregation with directional scores, quality, confidence, themes, contradictions, missing confirmations, and narrative.
- Reused one shadow-only result across DecisionContext, DecisionPipeline, PipelineResults, DashboardApplicationResult, Market Status, and the additive Institutional Evidence panel.
- Preserved recommendation, confidence, safety-gate, strike-selection, planning, persistence, export, and execution behaviour.

## Sprint 17B — Decision Confidence Validation & Ranking Readiness v1
- Added immutable, deterministic confidence-history validation for trend, stability, pillar agreement, readiness persistence, ranking eligibility, and material change detection.
- Added shadow recommendation comparison, conservative missing-data degradation, and configuration-driven thresholds without changing live CE/PE/WAIT decisions.
- Reused one validation result through DecisionContext, DecisionPipeline, PipelineResults, DashboardApplicationResult, Market Status, and the additive validation panel.
# Sprint 18 — Trade Opportunity Ranking v1

- Added immutable option-opportunity and trade-opportunity-ranking contracts.
- Added a repository-free, configuration-driven ranking engine with eligibility,
  normalization, liquidity/spread, activity, Greeks, IV, moneyness, expiry,
  direction, manipulation and confidence evaluation.
- Exposed one shared informational ranking through DecisionContext,
  PipelineResults, DashboardApplicationResult and the additive dashboard panel.
- Added deterministic behavioural coverage and a Sprint 18 review package.
- The live CE/PE/WAIT recommendation, confidence, SafetyGatePolicy, legacy strike
  ranking, Trade Planner and AI Trade Opportunity remain unchanged.
# Sprint 18.3A — Compression Intelligence Modernization

- Restored calculated, immutable compression intelligence on the current typed
  decision architecture, including normalized candle analytics, release states,
  safe degradation, evidence, contradictions, and quality reporting.
- Integrated one shared result before manipulation and exposed its diagnostics in
  the existing dashboard section without changing recommendation formulas.
# Sprint 18.4A — Historical Replay Backend Foundation

- Added typed LIVE, HISTORICAL_REPLAY, and SAMPLE_DATA provider contracts.
- Added immutable point-in-time replay requests and validation metadata.
- Added completed-candle cutoff enforcement, option snapshot selection, history
  isolation, deterministic samples, chunked downloading, and a local candle cache.
- Preserved existing decision formulas and the default live dashboard path.

## Sprint 18.4B — Historical Replay User Experience

- Added typed LIVE, HISTORICAL_REPLAY, and SAMPLE_DATA workspace selection without live fallback.
- Added replay controls, actual-candle navigation, metadata diagnostics, isolated session state, frozen snapshots, deterministic sample scenarios, and separately revealed outcome previews.
- Added immutable replay timeline/outcome contracts and deterministic behavioural specifications.
- Preserved the existing Analyst Dashboard and CE/PE/WAIT decision contracts unchanged.

## Sprint 18.4C — Historical Market Lake Foundation
- Added an atomic, date-partitioned local Historical Market Lake with immutable raw, versioned intelligence, and separately versioned factual outcome layers.
- Added incremental historical ingestion, point-in-time checkpointed enrichment, outcome enrichment, typed queries, availability reporting, and minimal developer status controls.
- Added schema/engine manifests, corruption-safe reads, idempotent upserts, secret redaction, and behavioural coverage without changing CE/PE/WAIT logic or dashboard sections.
- Hardened dashboard-result serialization for typed and attribute-based pipeline results, added redacted enrichment diagnostics, and clarified full-remainder-of-session MFE semantics.
- Corrected the serialization boundary so typed provider identity persists while dashboard runtime provider/client objects remain excluded.

## Sprint 18.4D — Historical Analytics

- Added a typed Historical Analytics workspace over stored Historical Market Lake intelligence and factual outcomes.
- Added period/filter controls, independent coverage reporting, aggregate dashboard concepts, per-section drill-down, and filtered CSV/JSON export.
- Added a collapsed Developer → Market Lake panel wired through explicit existing-service callbacks; analysis never downloads, replays, enriches, or executes the Decision Pipeline.
- Preserved Live, Historical Replay, Sample Data, and existing CE/PE/WAIT behavior.

## Sprint 18.4D.1 — Upstox Historical Sync Manager
- Added injected authenticated Historical Candle V3 adapter with sanitized typed errors and no Live fallback.
- Added typed instrument/settings, immutable plans/results/progress, bounded chunking, normalization, missing-date storage, checkpoints, finite retry, cancellation, and resume.
- Added separate raw sync, intelligence enrichment, and factual outcome actions plus Historical Analytics developer controls and scoped cache invalidation.
- Added deterministic fake-based behavioral/security tests and review documentation; analytical formulas and CE/PE/WAIT are unchanged.

## Sprint 18.4D.2 — Historical Dashboard & Trade Review
- Added trader-facing coverage, aggregate dashboard, filtered review table, deterministic directional classifications, stored-evidence triggers/reasons, and frozen-record deep dives.
- Added explicit expired-option partial replay, derived candle chain, failure-isolated live Market Lake capture, and after-market finalization contracts.
- Confined raw JSON to collapsed Advanced Diagnostics and preserved all trading formulas and roadmap order.

## Sprint 18.4E — Historical Intelligence Index & Market Fingerprinting
- Added stable SHA-256 historical trade identities, immutable versioned decision-time semantic and numeric fingerprints, and explicit feature/token/opposite registries.
- Added a transactional indexed SQLite store, safe filtering/pagination, incremental build/checkpoints, generation-aware statistics cache, and preliminary relationship graph.
- Preserved Market Lake files, outcome separation, replay no-look-ahead, CE/PE/WAIT decisions, dashboards, and all analytical formulas.
