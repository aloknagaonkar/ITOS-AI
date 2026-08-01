# Sprint 13 Files Changed

## Added
- `itos_platform/positioning_intelligence.py`
- `tests/test_positioning_intelligence.py`
- Sprint 13 files under `review/docs/` and mirrored modified files under `review/source/`

## Modified
- `itos_platform/decision_context.py`
- `itos_platform/decision_pipeline.py`
- `itos_platform/__init__.py`
- `dashboard_application_service.py` (exposure remains via the pipeline compatibility mapping)
- `app.py`
- `CHANGELOG.md`

## Deleted
None.

## Sprint 13 corrective patch
- Modified `itos_platform/positioning_intelligence.py` for canonical dependency degradation and side-specific premium flags.
- Modified `tests/test_positioning_intelligence.py` with focused regression coverage.
- Updated the Sprint 13 review documentation and corresponding files in `review/source/`.

## Typed boundary corrective patch
- `itos_platform/positioning_intelligence.py`: preserves typed versus legacy input mode through normalization.
- `tests/test_positioning_intelligence.py`: adds typed guard, fallback isolation, legacy parity, and options-independence regressions.
- Mirrored both modified Python files under `review/source/` and updated Sprint 13 review documentation.

## Runtime-source guard application
- Applied the typed-context guard directly to `itos_platform/positioning_intelligence.py`.
- Refreshed `review/source/itos_platform/positioning_intelligence.py` strictly as an identical copy of the production file.
- Tests were not modified or weakened.
