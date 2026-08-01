# Known Issues

- The full pytest suite was not run in the Codex environment and must pass locally before merge.
- `DecisionContext.engine_results` remains mutable temporarily for legacy downstream engine adapters.
- `DashboardApplicationResult.values` remains a dynamic dictionary for Streamlit compatibility even though the pipeline output itself is typed and frozen.
- A critical engine exception propagates rather than returning a partial result. This deliberately preserves the prior fail-closed behaviour: AI packaging and later writes are not reached.
- The Sprint 8 high-level types are intentionally not exported from `itos_platform`; callers must import them from `itos_platform.decision_pipeline` or `itos_platform.safety_gate_policy` to preserve the acyclic import boundary.
- Context propagation now creates one immutable `DecisionContext` replacement per engine; the contained provider-native market-data objects remain compatibility references and are not deep-copied.
