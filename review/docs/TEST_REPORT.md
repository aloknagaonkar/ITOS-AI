# Test Report

Behavioural tests were added in `tests/test_manipulation_intelligence.py` for genuine moves, failed moves, sweeps, traps, rejection, follow-through, context agreement/contradiction, malformed inputs, immutable/clamped output, instance parity and recommendation neutrality.

**pytest not executed by Codex — local validation required.**

Required local validation:

```text
python -m pytest -q
streamlit run app.py
```
