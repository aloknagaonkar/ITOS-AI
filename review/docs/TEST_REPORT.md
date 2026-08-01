# Sprint 13 Test Report

Deterministic behavioural coverage was added for futures matrices, neutral/missing/proxy data, writing and buying confirmation, conflicts, liquidity, IV, Greeks, premium data, location and volume context, malformed inputs, confidence clamping, immutability, and dashboard-facing contracts.

**pytest not executed by Codex — local validation required.**

Local validation commands:

- `python -m pytest -q`
- `streamlit run app.py`

## Follow-up correction

The two missing-context behavioural cases now remove each dependency from both its named `DecisionContext` field and `engine_results` before analysis, and assert the dependency is genuinely absent. A separate DecisionContext contract test proves restoration occurs when the mapping contains a value and absence is preserved when both representations omit it.
