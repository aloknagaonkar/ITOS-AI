# Architecture Notes

- `MarketSnapshot` remains point-in-time market data only.
- `DecisionContext` owns decision-layer dependencies, including institutional summary, decision history, strike history, and engine results.
- The application service, not `InstitutionalFlowEngine`, reads repositories.
- Each migrated engine has exactly one private `_adapt_input` boundary for typed and legacy inputs; calculations are shared after adaptation.
- `engine_results` remains the incremental compatibility registry used by the frozen context during ordered pipeline execution.
- Engine order, gates, recommendation mutation, persistence, and dashboard result keys remain unchanged.
