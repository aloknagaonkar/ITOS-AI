# Historical Analysis Orchestrator

`HistoricalAnalysisOrchestrator` is the application boundary for `PLAN → DOWNLOAD_UNDERLYING → DOWNLOAD_OPTIONS → BUILD_INTELLIGENCE → BUILD_OUTCOMES → BUILD_INDEX → PREPARE_ANALYTICS → COMPLETE`. It coordinates existing callbacks and owns no analytical formulas.

Requests, progress, date status and results are frozen dataclasses. Every run receives a stable UUID (or caller-supplied resume ID). The JSON checkpoint store writes atomically after each stage and contains serializable request/progress values only—never OAuth tokens, providers, clients, database connections or stack traces. Checkpoints survive process restart and preserve source work if a later stage fails.

Cancellation is observed at safe stage boundaries and reports `CANCELLED`; completed work remains intact. Disabled stages report `SKIPPED`. Historical option failure reports `PARTIAL` and candle-only processing continues. Intelligence uses the existing point-in-time runner, outcomes use the existing factual outcome service without rerunning decisions, and index updates occur only after intelligence/outcome stages. An index failure cannot delete Market Lake data. Analytics preparation is last and its immutable stored result is returned directly to the UI.

Failure messages are sanitized at the UI boundary. Retrying uses missing-only defaults; explicit rebuild flags override that behavior. Operational SQLite, Market Lake, and Historical Index SQLite remain separate.
