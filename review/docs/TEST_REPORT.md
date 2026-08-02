# Test Report

Behavioural tests were added in `tests/test_manipulation_intelligence.py` for genuine moves, failed moves, sweeps, traps, rejection, follow-through, context agreement/contradiction, malformed inputs, immutable/clamped output, instance parity and recommendation neutrality.

The failed-acceptance cases now assert false-breakout/false-breakdown identity
independently from liquidity sweeps. Dedicated upside and downside sweep fixtures
must exceed the unchanged production rejection threshold, and a regression test
proves that a valid false breakdown need not be a liquidity sweep.

**pytest not executed by Codex — local validation required.**

Required local validation:

```text
python -m pytest -q
streamlit run app.py
```
