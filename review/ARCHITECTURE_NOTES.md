# Architecture Notes

## Architectural Decisions
`MarketSnapshot` is frozen and restricted to option results, intelligence, institutional point-in-time inputs, and the capture/refresh marker. Recommendation state, engine results, histories, and repositories are deliberately excluded. `DecisionContext` owns decision-stage inputs and references (rather than copies) the canonical snapshot.

Dashboard execution constructs the snapshot after recommendation creation but before the market-cycle call, then passes that exact instance to market-cycle and data-health engines. After history reads and cycle analysis it constructs one context and passes that exact instance to recommendation stability.

## Compatibility Adapter Introduced
`DecisionContext.from_legacy` converts existing mapping inputs to the typed contract. `RecommendationStabilityEngine.analyze` performs only type dispatch; both paths execute the same calculation body.

## Why It Exists
External and older internal callers can continue passing dictionaries while typed orchestration becomes the preferred API, avoiding a flag-day migration and avoiding duplicated business logic.

## Temporary Technical Debt
- Most remaining engines retain mapping-oriented annotations and access patterns.
- `MarketSnapshot.get` provides a narrow mapping-like bridge for those engines.
- Data-health recommendation availability is constructor-injected because recommendation state cannot be stored in `MarketSnapshot`.

## Planned Cleanup
Migrate downstream engines to explicit typed inputs, inventory external legacy callers, deprecate mapping input, and eventually remove mapping compatibility after a communicated transition period.

## Risks
Callers may rely on undocumented dictionary keys. The adapter preserves unknown legacy keys in `DecisionContext.runtime`, but explicit contract fields should be added only when an engine truly requires them.

## Future Migration Recommendations
Keep snapshots immutable and market-only, keep repositories in the application layer, add contract parity tests for each migrated engine, and retain object-identity characterization tests in orchestration.
