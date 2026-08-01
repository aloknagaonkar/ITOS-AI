# Sprint Summary

## Sprint Name
Sprint 3 – Migrate RecommendationStabilityEngine to typed context

## Objective
Move recommendation-stability evaluation to a typed decision contract without changing recommendation, stability, safety, dashboard, or trading behavior.

## Architecture Changes
- Introduced a canonical, immutable `MarketSnapshot` containing point-in-time market inputs only.
- Introduced an immutable `DecisionContext` containing the snapshot, current recommendation, cycle result, histories, and runtime configuration.
- Changed recommendation stability's preferred input to `DecisionContext`; legacy mappings are converted once at the engine boundary.
- Dashboard orchestration now constructs and reuses one snapshot and one context.

## Files Added
- `itos_platform/decision_context.py`
- `tests/test_stability_typed_context.py`
- Six documents under `review/`

## Files Modified
- `CHANGELOG.md`
- `dashboard_application_service.py`
- `engines/data_health_engine.py`
- `engines/stability_engine.py`
- `itos_platform/__init__.py`
- `tests/test_dashboard_application_service.py`

## Files Removed
None.

## Backward Compatibility Notes
Legacy dictionary callers of `RecommendationStabilityEngine.analyze` remain supported by `DecisionContext.from_legacy`. Stability calculations and returned `EngineResult` fields are shared with the typed path rather than duplicated.

## Technical Debt
Other engines still primarily expose dictionary-shaped interfaces. Data-health decision availability is injected into the engine constructor while its point-in-time inputs use the canonical snapshot.

## Known Limitations
The container lacks project dependencies and cannot download them because package-index access returns HTTP 403. Consequently pytest cannot collect tests in this environment.

## Next Sprint Recommendation
Migrate the next decision-layer engines to `DecisionContext`, then remove compatibility adapters only after all external dictionary callers have migrated.
