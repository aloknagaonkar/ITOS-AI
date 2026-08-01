# Sprint Summary

## Sprint Name
Sprint 3 – Migrate RecommendationStabilityEngine to DecisionContext

## Delivered
- Extended the immutable decision-layer contract with explicit recommendation,
  engine-result, confidence-history, phase-history, and runtime-configuration fields.
- Kept `MarketSnapshot` limited to point-in-time market data.
- Added one private legacy adapter at the recommendation-stability boundary, so
  dictionary and typed inputs share the unchanged calculation.
- Wired one dashboard snapshot to market-cycle and data-health engines and one
  context to recommendation stability.
- Expanded parity and characterization coverage for direction, history quality,
  thresholds, object identity, caching, engine order, and safety vetoes.

## Behavioral Compatibility
Stability formulae, labels, trend and direction-change calculation, the 70% default
threshold, pass/fail behavior, recommendation mutation, safety vetoes, engine order,
session keys, persistence, and trading algorithms are unchanged.

## Validation Status
Static compilation and whitespace validation pass. The full pytest command was
run, but missing pandas and NumPy stop collection before tests execute. The sprint
is therefore not declared merge-gate complete in this environment.
