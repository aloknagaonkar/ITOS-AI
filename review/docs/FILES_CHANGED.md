# Files Changed

| File | Reason | Architectural impact | Backward compatibility |
|---|---|---|---|
| `itos_platform/institutional_metrics.py` | Typed contracts, schema adapter, settings, calculations | Adds repository-free institutional evidence boundary | Additive; no decisions consume it |
| `itos_platform/decision_context.py` | Carries shared metrics | Context owns one pipeline-scoped instance | Optional field defaults to `None` |
| `itos_platform/decision_pipeline.py` | Computes metrics after snapshot availability and exposes result | Adds documented early metrics stage | Existing engine sequence relative to each other unchanged |
| `itos_platform/__init__.py` | Public exports | Makes new contracts discoverable | Additive |
| `tests/test_institutional_metrics.py` | Behavioural deterministic coverage | Verifies engine contract | Test-only |
| `CHANGELOG.md` | Sprint entry | Documents release foundation | None |
| `review/docs/*` | Review, formulas, validation, deferrals | Audit package | None |
| `review/source/*` | Path-preserving source review copy | Review-only mirror | None |
