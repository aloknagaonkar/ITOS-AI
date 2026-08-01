# Architecture Notes

- `MarketSnapshot` remains point-in-time provider data only.
- `DecisionContext` owns recommendation, runtime configuration, histories, repositories, and engine dependencies.
- Typed result fields support explicit construction; `engine_results` remains the live pipeline registry so results produced after context creation are visible without creating a second context.
- Every migrated engine adapts typed or mapping input once, then executes its existing calculation path.
- Dashboard construction counts remain exactly one snapshot and one context per execution, including cached execution.
