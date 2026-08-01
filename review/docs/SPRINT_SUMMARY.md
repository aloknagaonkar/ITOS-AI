# Sprint 6 Summary

Sprint 6 migrates `InstitutionalRadarEngine`, `InstitutionalFlowEngine`, `InstitutionalConfidenceEngine`, and `InstitutionalDecisionMatrixEngine` to prefer `DecisionContext`. Each engine retains its public `analyze({...})` compatibility path and runs typed and legacy calls through one private adapter into the existing calculations.

`DashboardApplicationService` still creates one `MarketSnapshot` and one `DecisionContext`. The four migrated engines now receive that same context instance in their existing execution positions. Decision and strike history are carried by `DecisionContext`; repositories remain owned by the application service and market-only data remains in `MarketSnapshot`.

Malformed or absent flow histories degrade to the existing warming-up/WAIT result. Malformed strike history is ignored rather than producing directional evidence.
