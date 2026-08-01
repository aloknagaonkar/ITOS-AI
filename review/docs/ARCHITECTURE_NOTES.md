# Architecture Notes

- `MarketSnapshot` remains frozen and contains point-in-time market data only.
- `DecisionContext` now explicitly carries the optional institutional decision input because Pattern Recognition genuinely requires it; it is not placed in the snapshot.
- Every migrated engine exposes the unchanged `analyze(...)` method and owns exactly one private `_adapt_input` boundary adapter.
- Adapters translate typed contexts to the legacy-shaped internal model, leaving all scoring, thresholds, explanations, metadata, and degradation branches unchanged.
- The dashboard creates one snapshot and one context. It registers intermediate results in the context's existing `engine_results` mapping for downstream use rather than constructing replacement contexts.
