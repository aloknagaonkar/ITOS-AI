# Sprint 8 Test Report

## Codex validation

- The required `python -m py_compile` syntax validation was executed for all Python files modified by the state-propagation correction.
- `git diff --check` was executed as the required patch whitespace validation.
- **pytest not executed by Codex.**
- **Full local validation is required before merge:** `python -m pytest -q`.

## Behavioural coverage added or retained

The application-service characterization now verifies that every context-aware engine receives a distinct immutable `DecisionContext`, that every such context retains the canonical `MarketSnapshot`, and that its `engine_results` contains the expected results from all earlier stages. It specifically verifies that Recommendation Stability receives the completed Market Cycle result and that the final context contains all named outputs. Existing coverage continues to characterize engine order, result wiring, cached execution, safety vetoes, failure propagation, dashboard compatibility, typed aliases, and fresh-process import boundaries. The full local suite remains the acceptance gate.
