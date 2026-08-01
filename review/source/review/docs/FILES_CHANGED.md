# Files Changed

| File | Reason | Architectural impact | Backward compatibility |
|---|---|---|---|
| `engines/institutional_intelligence.py` | Radar consumes typed OI-change totals | Metrics forwarded through private adapter | Legacy summary fallback retained |
| `engines/institutional_flow.py` | Flow and Confidence consume typed motion/liquidity | Shared metrics forwarded by identity | Legacy history/result mappings retained |
| `engines/trade_planner.py` | Decision Matrix consumes typed liquidity fallback | Shared metrics forwarded by identity | Existing component takes precedence |
| `itos_platform/decision_context.py` | Type canonical metrics field | Documents typed context boundary | Constructor field/default unchanged |
| `itos_platform/decision_pipeline.py` | Injectable once-only metrics producer | One calculation and shared instance | Default construction unchanged |
| `tests/test_institutional_flow_context.py` | Add identity and parity characterization | Verifies adapter contract behaviorally | Test-only |
| `CHANGELOG.md` | Record Sprint 10 | Documentation only | None |
| `review/docs/*` | Sprint review package | Documentation only | None |
| `review/source/*` | Modified-source package | Review artifact only | None |

## Modified-source package files

Every entry below is a review-only mirror: its reason is to provide the requested modified source, its architectural impact is none, and its backward-compatibility impact is none.

- `review/source/CHANGELOG.md`
- `review/source/engines/institutional_flow.py`
- `review/source/engines/institutional_intelligence.py`
- `review/source/engines/trade_planner.py`
- `review/source/itos_platform/decision_context.py`
- `review/source/itos_platform/decision_pipeline.py`
- `review/source/tests/test_institutional_flow_context.py`
- `review/source/review/docs/ARCHITECTURE_NOTES.md`
- `review/source/review/docs/BUILD_LOG.txt`
- `review/source/review/docs/FILES_CHANGED.md`
- `review/source/review/docs/FUTURE_RECOMMENDATIONS.md`
- `review/source/review/docs/KNOWN_ISSUES.md`
- `review/source/review/docs/METRICS_ADOPTION_MAP.md`
- `review/source/review/docs/SELF_REVIEW.md`
- `review/source/review/docs/SPRINT_SUMMARY.md`
- `review/source/review/docs/TEST_REPORT.md`

Sprint 9 mirror files for unchanged sources were deleted from `review/source/`: `dashboard_application_service.py`, `itos_platform/__init__.py`, `itos_platform/institutional_metrics.py`, `itos_platform/safety_gate_policy.py`, `tests/test_dashboard_application_service.py`, `tests/test_decision_pipeline.py`, and `tests/test_institutional_metrics.py`. Their removal keeps the Sprint 10 package limited to modified files; it has no runtime or compatibility impact.
