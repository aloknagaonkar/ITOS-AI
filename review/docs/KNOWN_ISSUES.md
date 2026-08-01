# Known Issues

- The full pytest suite was not run in the Codex environment and must pass locally before merge.
- `DecisionContext.engine_results` remains mutable temporarily for legacy downstream engine adapters.
- `DashboardApplicationResult.values` remains a dynamic dictionary for Streamlit compatibility even though the pipeline output itself is typed and frozen.
- A critical engine exception propagates rather than returning a partial result. This deliberately preserves the prior fail-closed behaviour: AI packaging and later writes are not reached.
