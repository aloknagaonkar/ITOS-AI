# Circular-Import Fix Files Changed

| File | Reason changed | Architectural impact | Backward-compatibility impact |
|---|---|---|---|
| `itos_platform/__init__.py` | Remove eager high-level imports | Restores low-level package boundary and breaks engine/package cycle | Newly introduced Sprint 8 root exports are removed; direct module imports remain public |
| `itos_platform/decision_pipeline.py` | Import concrete engine modules | Prevents re-entry through the `engines` barrel | Engine classes, order, inputs, and results are unchanged |
| `dashboard_application_service.py` | Import contracts and pipeline directly | Makes dependency direction explicit | Service API and dashboard result are unchanged |
| `tests/test_dashboard_application_service.py` | Import context contracts directly | Exercises supported boundary | Test behaviour unchanged |
| `tests/test_decision_pipeline.py` | Import high-level types directly and add fresh-process regression test | Guards package initialization order | No production compatibility impact |
| `review/docs/ARCHITECTURE_NOTES.md` | Document dependency-boundary correction | Records rationale and avoided alternatives | None |
| `review/docs/BUILD_LOG.txt` | Capture required validation output | Audit evidence | None |
| `review/docs/TEST_REPORT.md` | Record import regression coverage and pytest status | Audit documentation | None |
| `review/docs/KNOWN_ISSUES.md` | Document intentional direct-import API | Makes root-export limitation explicit | Guides callers to supported imports |
| `review/docs/FILES_CHANGED.md` | Inventory every fix file | Review documentation | None |
| `review/source/itos_platform/__init__.py` | Review copy of modified package root | Review artifact | None |
| `review/source/itos_platform/decision_pipeline.py` | Review copy of modified pipeline | Review artifact | None |
| `review/source/dashboard_application_service.py` | Review copy of modified service | Review artifact | None |
| `review/source/tests/test_dashboard_application_service.py` | Review copy of modified service test | Review artifact | None |
| `review/source/tests/test_decision_pipeline.py` | Review copy of modified pipeline/import test | Review artifact | None |
