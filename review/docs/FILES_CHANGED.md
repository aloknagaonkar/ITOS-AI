# Files Changed

| File | Reason changed | Architectural impact | Backward-compatibility impact |
|---|---|---|---|
| `CHANGELOG.md` | Record Sprint 8 | Documents new boundary | None |
| `dashboard_application_service.py` | Delegate engine orchestration and map typed results | Service becomes I/O/application boundary | Preserves result fields, persistence, session state, and AI inputs |
| `itos_platform/__init__.py` | Export new contracts | Makes pipeline/policy public | Additive exports only |
| `itos_platform/decision_pipeline.py` | Add pipeline and frozen result contract | Central orchestration and authoritative outputs | Compatibility aliases/mapping retained |
| `itos_platform/safety_gate_policy.py` | Centralize monotonic vetoes | One typed safety decision | Existing statuses, blockers, and thresholds retained |
| `tests/test_dashboard_application_service.py` | Characterize delegation and engine order | Tests new boundary behaviourally | Retains legacy contract assertions |
| `tests/test_decision_pipeline.py` | Cover typed wiring and safety policy | Direct contract coverage | Verifies legacy aliases |
| `review/docs/SPRINT_SUMMARY.md` | Sprint review summary | Documentation only | None |
| `review/docs/TEST_REPORT.md` | Record validation constraints and coverage | Documentation only | None |
| `review/docs/BUILD_LOG.txt` | Capture exact permitted command output | Audit evidence only | None |
| `review/docs/FILES_CHANGED.md` | Inventory every sprint file | Documentation only | None |
| `review/docs/ARCHITECTURE_NOTES.md` | Explain decisions, compatibility, failure, rollback | Documentation only | None |
| `review/docs/KNOWN_ISSUES.md` | Record known limitations | Documentation only | None |
| `review/docs/SELF_REVIEW.md` | Required structured self-assessment | Documentation only | None |
| `review/docs/FUTURE_RECOMMENDATIONS.md` | Record out-of-scope ideas | Prevents scope creep | None |
| `review/docs/PIPELINE_ORDER.md` | Record before/after order, dependencies, vetoes | Characterization reference | Confirms unchanged engine order |
| `review/source/CHANGELOG.md` | Modified-source review copy | Review artifact only | None |
| `review/source/dashboard_application_service.py` | Modified-source review copy | Review artifact only | None |
| `review/source/itos_platform/__init__.py` | Modified-source review copy | Review artifact only | None |
| `review/source/itos_platform/decision_pipeline.py` | Modified-source review copy | Review artifact only | None |
| `review/source/itos_platform/safety_gate_policy.py` | Modified-source review copy | Review artifact only | None |
| `review/source/tests/test_dashboard_application_service.py` | Modified-source review copy | Review artifact only | None |
| `review/source/tests/test_decision_pipeline.py` | Modified-source review copy | Review artifact only | None |
