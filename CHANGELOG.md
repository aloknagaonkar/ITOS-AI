# Changelog

## Unreleased
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
