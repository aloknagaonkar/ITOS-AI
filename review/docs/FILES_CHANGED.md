# Files Changed

| File | Reason | Architectural impact | Backward compatibility |
|---|---|---|---|
| `itos_platform/volume_structure.py` | Add immutable model, settings, and engine | New informational analysis stage | Additive only |
| `itos_platform/decision_context.py` | Carry shared result | Extends canonical context/result aliases | Optional field preserves callers |
| `itos_platform/decision_pipeline.py` | Execute stage after location and expose result | One shared instance in pipeline | Additive result field/mapping |
| `itos_platform/__init__.py` | Export public contracts | Public API addition | Existing exports unchanged |
| `app.py` | Add status, behaviour, and metrics preview | Presentation consumes pipeline facts only | Primary cards/decisions unchanged |
| `tests/test_volume_structure.py` | Add deterministic behavioural contracts | Characterizes Sprint 12 boundaries | Test-only |
| `CHANGELOG.md` | Record Sprint 12 | Release documentation | None |
| `review/docs/*` | Provide rules and review evidence | Review-only | None |
| `review/source/*` | Preserve modified-source review package | Review-only copies | None |
| `review/docs/ROADMAP_PROGRESS.md` | Record feature-register progress and deferrals | Review-only roadmap traceability | None |
