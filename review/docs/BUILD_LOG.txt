# Sprint 18.4F.2 Hardening Validation Report

## Commands and actual outputs

1. `python -m py_compile app.py itos_platform/historical_analysis_orchestrator.py ui/historical_analytics_workspace.py tests/test_historical_analysis_orchestrator.py tests/test_simplified_historical_analysis_ui.py`
   - PASS (exit 0; no output).
2. `python -m pytest -q tests/test_historical_analysis_orchestrator.py tests/test_simplified_historical_analysis_ui.py tests/test_historical_pipeline_integration.py tests/test_historical_analytics.py tests/test_historical_trade_review.py`
   - PASS: `91 passed in 2.08s`.
3. `python -m pytest -q`
   - PASS: `602 passed in 8.92s`.
4. `git diff --check`
   - PASS (exit 0; no output).
5. `python -m streamlit run app.py --server.headless true --server.port 8767` and `curl -fsS http://127.0.0.1:8767/_stcore/health`
   - PASS: Streamlit reached ready state and health returned `ok`; server then stopped.

Focused behavioural coverage includes real result mapping, isolated date failure, existing versus downloaded data, one-date option partial status, intelligence failure isolation, pending outcomes, index failure isolation, actual counts, cadence propagation, schema-safe checkpoint load, new-instance resume, atomic-date cancellation, failed-only retry, index-only retry, final Ready/Candle-only/Retry Required states, a reusable progress presenter, and automatic prepared analytics.

No authenticated Upstox call was made. No order was placed. No credential or OAuth token was printed or persisted. Manual UI validation: NOT RUN — DEVELOPER VALIDATION REQUIRED.
