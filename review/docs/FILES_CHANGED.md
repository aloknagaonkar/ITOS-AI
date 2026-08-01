# Decision Context Propagation Fix — Files Changed

| File | Reason changed | Architectural impact | Backward-compatibility impact |
|---|---|---|---|
| `itos_platform/decision_pipeline.py` | Advance context after each engine with `dataclasses.replace()` and return the final context | Preserves immutable state while exposing completed results downstream | Engine order, inputs, calculations, and named dashboard mapping remain unchanged |
| `dashboard_application_service.py` | Adopt the pipeline's final accumulated context | Dashboard result now exposes the context actually completed by the pipeline | Existing `decision_context` result field remains present |
| `tests/test_dashboard_application_service.py` | Characterize per-stage populated contexts | Verifies every context-aware engine sees prior results and the canonical snapshot | Updates identity assertions for immutable replacements |
| `tests/test_decision_pipeline.py` | Supply and exclude the new final-context contract field in wiring assertions | Covers typed final context without treating it as an engine result | Existing result aliases remain unchanged |
| `review/docs/ARCHITECTURE_NOTES.md` | Explain immutable propagation design | Documents replacement semantics | None |
| `review/docs/BUILD_LOG.txt` | Capture permitted validation | Audit evidence | None |
| `review/docs/TEST_REPORT.md` | Record new characterization and pytest status | Audit documentation | None |
| `review/docs/KNOWN_ISSUES.md` | Record shallow immutable-boundary assumption | Documents provider-native reference behavior | None |
| `review/docs/FILES_CHANGED.md` | Inventory every modified fix file | Review documentation | None |
| `review/source/itos_platform/decision_pipeline.py` | Review copy of modified pipeline | Review artifact | None |
| `review/source/dashboard_application_service.py` | Review copy of modified service | Review artifact | None |
| `review/source/tests/test_dashboard_application_service.py` | Review copy of modified characterization test | Review artifact | None |
| `review/source/tests/test_decision_pipeline.py` | Review copy of modified result-contract test | Review artifact | None |
