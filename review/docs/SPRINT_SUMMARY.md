# Sprint 8 Summary

Sprint 8 introduces an architectural boundary around the existing decision sequence. `DashboardApplicationService` still acquires data, reads and writes repository history, constructs exactly one snapshot and context, invokes AI trade packaging, and returns the legacy dashboard fields. Engine construction, wiring, result registration, recommendation metadata attachment, and existing safety gates now execute inside `DecisionPipeline`.

`PipelineResults` is the authoritative frozen output. The service expands its named values into `DashboardApplicationResult.values`, including the legacy `ice_result` and `smi_result` aliases. No indicator, formula, threshold, weight, persistence schema, Upstox path, dashboard layout, or order-execution feature was changed.
