# Files Changed

| Filename | Reason changed | Architectural impact | Backward compatibility impact |
|---|---|---|---|
| `CHANGELOG.md` | Record Sprint 7. | Documentation only. | None. |
| `dashboard_application_service.py` | Pass the canonical context to four engines and register dependencies. | Preserves one snapshot/context and execution order. | Dashboard outputs, state keys, and persistence remain unchanged. |
| `engines/core_intelligence.py` | Add typed adapters for regime, SMI, and energy. | Canonical typed boundary with one calculation path. | Legacy mappings remain accepted with identical calculations. |
| `engines/institutional_flow.py` | Add Early Warning typed adapter and blocked-input safety. | Reads upstream results from context. | Legacy mappings remain accepted; blocked recommendations degrade to WAIT. |
| `itos_platform/decision_context.py` | Expose scoped engine dependency fields. | Runtime results stay outside `MarketSnapshot`. | Existing constructors and `engine_results` aliases remain supported. |
| `tests/test_dashboard_application_service.py` | Characterize canonical instances and dependency wiring. | Protects orchestration boundaries and ordering. | Protects cached and legacy dashboard behavior. |
| `tests/test_market_state_context.py` | Add parity and safe-degradation cases. | Verifies the adapter architecture. | Explicitly protects dictionary callers. |
| `review/docs/SPRINT_SUMMARY.md` | Summarize delivery. | Documentation only. | None. |
| `review/docs/TEST_REPORT.md` | Record constrained validation and required local pytest. | Documentation only. | None. |
| `review/docs/BUILD_LOG.txt` | Capture complete authorized command output. | Documentation only. | None. |
| `review/docs/FILES_CHANGED.md` | Inventory every sprint file. | Documentation only. | None. |
| `review/docs/ARCHITECTURE_NOTES.md` | Explain snapshot/context boundaries. | Documents canonical ownership. | None. |
| `review/docs/KNOWN_ISSUES.md` | Record validation limitation. | Documentation only. | None. |
| `review/docs/SELF_REVIEW.md` | Record scope and safety review. | Documentation only. | None. |
| `review/docs/FUTURE_RECOMMENDATIONS.md` | Defer unrelated migration work. | Documentation only. | None. |
| `review/source/CHANGELOG.md` | Review copy of modified changelog. | Review artifact only. | None. |
| `review/source/dashboard_application_service.py` | Review copy of modified orchestration. | Review artifact only. | None. |
| `review/source/engines/core_intelligence.py` | Review copy of migrated engines. | Review artifact only. | None. |
| `review/source/engines/institutional_flow.py` | Review copy of Early Warning. | Review artifact only. | None. |
| `review/source/itos_platform/decision_context.py` | Review copy of contract. | Review artifact only. | None. |
| `review/source/tests/test_dashboard_application_service.py` | Review copy of characterization tests. | Review artifact only. | None. |
| `review/source/tests/test_market_state_context.py` | Review copy of parity tests. | Review artifact only. | None. |
| `review/source/engines/institutional_intelligence.py` | Removed obsolete prior-sprint review copy. | Keeps source package Sprint 7-only. | Production file is untouched. |
| `review/source/engines/trade_planner.py` | Removed obsolete prior-sprint review copy. | Keeps source package Sprint 7-only. | Production file is untouched. |
| `review/source/tests/test_institutional_flow_context.py` | Removed obsolete prior-sprint review copy. | Keeps source package Sprint 7-only. | Production test is untouched. |
