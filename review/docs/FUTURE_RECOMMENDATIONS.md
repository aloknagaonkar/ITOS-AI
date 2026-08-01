# Future Recommendations

These are observations only and were **not implemented** in Sprint 8:

- Migrate downstream engines from `DecisionContext.engine_results` to explicit typed dependencies, then remove the mutable registry.
- Replace the dynamic dashboard values contract with an explicitly typed presentation DTO after all `app.py` consumers migrate.
- Introduce structured pipeline failure results if product requirements prefer a rendered WAIT card over the current exception propagation.
- Split recommendation table-state alignment into a dedicated application mapper after downstream engines no longer consume it.
- Add dedicated CE and PE golden-fixture datasets maintained independently of orchestration mocks.
