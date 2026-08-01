# Architecture Notes

## Contract Boundary
`MarketSnapshot` remains frozen and market-only: option data, intelligence,
candles, timestamps, instrument selection, and data-quality facts. It does not
contain recommendations, engine results, or historical result DataFrames.

`DecisionContext` references the canonical snapshot and explicitly owns the current
recommendation, named engine results, confidence history, phase history, and runtime
configuration. Existing repository/configuration/session fields remain for backward
compatibility; histories are not hidden in repository containers.

## Compatibility Adapter
`RecommendationStabilityEngine._adapt_input` is the one conversion boundary for
legacy mappings. Typed and legacy calls then execute the same stability algorithm.
Unknown legacy settings are retained as runtime configuration.

## Dashboard Identity
Dashboard execution creates one `MarketSnapshot`, passes it by identity to
`MarketCycleEngine` and `DataHealthEngine`, creates one `DecisionContext`, and passes
that context to `RecommendationStabilityEngine`. The context points to the exact
same snapshot and names the cycle result as `engine_results["market_cycle"]`.

## Deferred Work
Other engines remain mapping-oriented and can migrate incrementally. The legacy
stability adapter should be removed only after external mapping callers have been
inventoried and deprecated.
