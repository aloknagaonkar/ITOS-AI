# Files Changed

| Filename | Reason modified | Architectural impact | Backward compatibility impact |
|---|---|---|---|
| `CHANGELOG.md` | Record Sprint 5. | Documentation only. | None. |
| `dashboard_application_service.py` | Pass one canonical context to migrated engines and register intermediate results. | Extends canonical context reuse across Structure Intelligence. | Engine order, results, gates, and session keys remain unchanged. |
| `engines/institutional_confirmation.py` | Add typed adapters to Candle DNA, Smart Candlestick, Institutional Structure, and False Breakout. | Moves four engines to the context boundary. | Legacy dictionaries remain accepted. |
| `engines/institutional_intelligence.py` | Add Pattern Recognition typed adapter. | Moves pattern analysis to the context boundary. | Legacy dictionaries remain accepted. |
| `itos_platform/decision_context.py` | Add optional institutional decision input. | Keeps derived runtime input outside immutable market data. | Additive constructor field with a default. |
| `tests/test_dashboard_application_service.py` | Characterize exact context reuse by migrated engines. | Guards orchestration identity and order. | Test only. |
| `tests/test_structure_intelligence_context.py` | Add parity, malformed/missing-data, and safety tests. | Verifies typed/legacy boundary equivalence. | Test only. |
| `review/docs/*` | Provide required Sprint 5 review documentation. | Review artifact only. | None. |
| `review/source/*` | Mirror modified source and test files. | Review artifact only. | None. |
