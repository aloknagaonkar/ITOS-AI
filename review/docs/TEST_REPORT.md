# Sprint 8 Test Report

## Codex validation

- `python -m py_compile <all modified Python files>`: required syntax validation only.
- `git diff --check`: required patch whitespace validation only.
- **pytest not executed by Codex.**
- **Full local validation is required before merge:** `python -m pytest -q`.

## Behavioural coverage added or retained

The tests characterize engine order, result wiring, canonical snapshot/context identity, cached execution without acquisition or writes, existing false-breakout and validation vetoes, missing candles, acquisition/pipeline failure propagation without an AI BUY, malformed critical input, unhealthy data, dashboard result compatibility, and typed/legacy output aliases. The existing fixtures continue to exercise valid recommendation packaging; the full local suite is the acceptance gate for bullish and bearish parity.
