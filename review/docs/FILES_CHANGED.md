# Sprint 18.4F.2 Hardening Files Changed

## Production
- `app.py` — propagates selected intelligence cadence.
- `itos_platform/historical_analysis_orchestrator.py` — actual result mapping, per-date dependencies/progress, schema-v2 checkpoint load/resume, cancellation, and targeted retries.
- `ui/historical_analytics_workspace.py` — reusable progress placeholder/view models and cancel/retry actions.

## Tests
- `tests/test_historical_analysis_orchestrator.py` — behavioural orchestration, isolation, cadence, checkpoint, restart, cancellation and retry coverage.
- `tests/test_simplified_historical_analysis_ui.py` — pure progress view-model and reusable presenter tests.

## Documentation and review
- `CHANGELOG.md`
- `review/docs/ARCHITECTURE_NOTES.md`
- `review/docs/BUILD_LOG.txt`
- `review/docs/FILES_CHANGED.md`
- `review/docs/HISTORICAL_ANALYSIS_ORCHESTRATOR.md`
- `review/docs/HISTORICAL_PIPELINE_INTEGRATION_RULES.md`
- `review/docs/KNOWN_ISSUES.md`
- `review/docs/SIMPLIFIED_HISTORICAL_ANALYSIS_UX.md`
- `review/docs/SPRINT_SUMMARY.md`
- `review/docs/TEST_REPORT.md`
- Exact path-preserving mirrors of modified application/test sources and `CHANGELOG.md` under `review/source/`.

No files were deleted. Analytical formulas and database technologies were not changed.
