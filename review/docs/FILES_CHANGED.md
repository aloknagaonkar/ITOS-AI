# Files Changed

| File | Reason | Architectural impact | Backward compatibility |
|---|---|---|---|
| `itos_platform/market_location.py` | Add typed model, settings, engine | New informational domain component | Additive |
| `itos_platform/decision_context.py` | Carry canonical result | Extends immutable context | Optional field; compatible |
| `itos_platform/decision_pipeline.py` | Execute/expose engine once | Adds pipeline stage/result | Dashboard mapping additive; decision behavior unchanged |
| `itos_platform/__init__.py` | Export public types | Extends package API | Additive |
| `app.py` | Add collapsed preview | Presentation-only consumer | Primary cards/state unchanged |
| `tests/test_market_location.py` | Behavioral coverage | Validates new boundary | Test-only |
| `CHANGELOG.md` | Record Sprint 11 | Documentation | None |
| `review/docs/*` | Review and validation records | Review artifact | None |
| `review/source/*` | Modified-source review package | Review artifact | None |
