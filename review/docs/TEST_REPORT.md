# Sprint 5 Test Report

## Required static validation

- `python -m py_compile dashboard_application_service.py engines/institutional_confirmation.py engines/institutional_intelligence.py itos_platform/decision_context.py tests/test_dashboard_application_service.py tests/test_structure_intelligence_context.py` — passed.
- `git diff --check` — passed.

## Targeted tests

Command: `python -m pytest tests/test_structure_intelligence_context.py tests/test_dashboard_application_service.py -q`

Result: not executed beyond collection because the environment does not contain pandas. Pytest reported two collection errors and ran no tests. No dependency installation was attempted, and production code was not modified to accommodate the runner.

Planned coverage includes all five migrated engines, identical score/vote/confidence/explanation/metadata, malformed and missing candle/structure inputs, cached service execution, canonical object identity, unchanged order, compatibility, safe degradation, and false-breakout blocking.
