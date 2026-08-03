# Sprint 18.4F.1 Files Changed

## Production
- `app.py` — shared composition, callbacks, source/navigation resolution, and failure-isolated Live capture.
- `itos_platform/historical_pipeline.py` — shared pipeline composition and point-in-time runner.
- `itos_platform/historical_intelligence_index.py` — SQLite pragmas and integrity diagnostics.
- `ui/historical_analytics_workspace.py` — explicit pipeline/index/option/finalization actions and Trade Review handoff.
- `ui/historical_similarity_workspace.py` — historical, Live, and Replay source resolution plus match deep dive/navigation.
- `ui/replay_workspace.py` — candidate timestamp loading and return navigation.

## Tests
- `tests/test_historical_pipeline_integration.py` — shared dependency, real SQLite build, and single-invocation runner integration tests.

## Documentation/review
- `CHANGELOG.md`
- `review/docs/ARCHITECTURE_NOTES.md`
- `review/docs/BUILD_LOG.txt`
- `review/docs/DATABASE_OPERATING_MODEL.md`
- `review/docs/FILES_CHANGED.md`
- `review/docs/HISTORICAL_PIPELINE_INTEGRATION_RULES.md`
- `review/docs/KNOWN_ISSUES.md`
- `review/docs/ROADMAP_PROGRESS.md`
- `review/docs/SELF_REVIEW.md`
- `review/docs/SPRINT_SUMMARY.md`
- `review/docs/TEST_REPORT.md`

## Review source (exact mirrors)
- `review/source/CHANGELOG.md`
- `review/source/app.py`
- `review/source/itos_platform/historical_intelligence_index.py`
- `review/source/itos_platform/historical_pipeline.py`
- `review/source/tests/test_historical_pipeline_integration.py`
- `review/source/ui/historical_analytics_workspace.py`
- `review/source/ui/historical_similarity_workspace.py`
- `review/source/ui/replay_workspace.py`

No files were deleted from the application. The three stale flat review/source files from Sprint 18.4F were replaced by path-preserving Sprint 18.4F.1 mirrors.
