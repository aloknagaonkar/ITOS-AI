# Sprint 8 Test Report

## Codex validation

- The required targeted `python -m py_compile` command was executed for the circular-import correction.
- `git diff --check` was executed as the required patch whitespace validation.
- **pytest not executed by Codex.**
- **Full local validation is required before merge:** `python -m pytest -q`.

## Behavioural coverage added or retained

The tests characterize engine order, result wiring, canonical snapshot/context identity, cached execution without acquisition or writes, existing false-breakout and validation vetoes, missing candles, acquisition/pipeline failure propagation without an AI BUY, malformed critical input, unhealthy data, dashboard result compatibility, and typed/legacy output aliases. A fresh-process import-boundary test now imports `engines`, `itos_platform`, `itos_platform.decision_pipeline`, and `dashboard_application_service` in the failure-producing order so the collection-time circular import cannot regress unnoticed. The full local suite remains the acceptance gate.
