# Files Changed

| File | Reason changed | Architectural impact | Backward-compatibility impact |
|---|---|---|---|
| `itos_platform/decision_context.py` | Add decision, strike, and stability history dependencies. | Keeps histories in the decision layer rather than the market snapshot. | Additive constructor fields with defaults. |
| `engines/institutional_intelligence.py` | Add the radar typed/legacy adapter. | Radar consumes the canonical snapshot and context dependencies. | Legacy mappings remain supported. |
| `engines/institutional_flow.py` | Add flow and confidence adapters plus malformed-history safeguards. | Flow consumes histories from context and confidence consumes its result registry. | Legacy mappings and cold-history behavior remain supported. |
| `engines/trade_planner.py` | Add the decision-matrix adapter. | Matrix dependencies come from the context result registry. | Legacy mappings remain supported. |
| `dashboard_application_service.py` | Route all four engines through one context and publish ordered results. | Enforces canonical context identity throughout the scoped pipeline. | Engine order, result keys, persistence, and gates are retained. |
| `tests/test_institutional_flow_context.py` | Add parity and safe-degradation characterization tests. | Covers typed boundaries for all four engines. | Verifies legacy output parity. |
| `tests/test_dashboard_application_service.py` | Characterize shared context and histories/results. | Verifies pipeline identity and result propagation. | Retains cached execution, order, and veto coverage. |
| `CHANGELOG.md` | Record Sprint 6 migration. | Documentation only. | None. |
| `review/docs/SPRINT_SUMMARY.md` | Summarize scoped delivery. | Documentation only. | None. |
| `review/docs/TEST_REPORT.md` | Record permitted validation and local pytest requirement. | Documentation only. | None. |
| `review/docs/BUILD_LOG.txt` | Preserve complete validation command output. | Documentation only. | None. |
| `review/docs/FILES_CHANGED.md` | Inventory the sprint patch. | Documentation only. | None. |
| `review/docs/ARCHITECTURE_NOTES.md` | Document context and repository boundaries. | Documentation only. | None. |
| `review/docs/KNOWN_ISSUES.md` | Record outstanding local validation. | Documentation only. | None. |
| `review/docs/SELF_REVIEW.md` | Record scope and architecture review. | Documentation only. | None. |
| `review/docs/FUTURE_RECOMMENDATIONS.md` | Defer out-of-scope cleanup. | Documentation only. | None. |
| `review/source/CHANGELOG.md` | Supply review copy of the modified changelog. | Review artifact only. | None. |
| `review/source/dashboard_application_service.py` | Supply review copy of modified orchestration. | Review artifact only. | None. |
| `review/source/engines/institutional_intelligence.py` | Supply review copy of modified radar source. | Review artifact only. | None. |
| `review/source/engines/institutional_flow.py` | Supply review copy of modified flow/confidence source. | Review artifact only. | None. |
| `review/source/engines/trade_planner.py` | Supply review copy of modified matrix source. | Review artifact only. | None. |
| `review/source/itos_platform/decision_context.py` | Supply review copy of modified contract. | Review artifact only. | None. |
| `review/source/tests/test_dashboard_application_service.py` | Supply review copy of modified dashboard tests. | Review artifact only. | None. |
| `review/source/tests/test_institutional_flow_context.py` | Supply review copy of new parity tests. | Review artifact only. | None. |
| `review/source/engines/institutional_confirmation.py` | Remove prior-sprint source review artifact so the package contains only Sprint 6 files. | Review artifact cleanup only. | None. |
| `review/source/tests/test_structure_intelligence_context.py` | Remove prior-sprint source review artifact so the package contains only Sprint 6 files. | Review artifact cleanup only. | None. |
