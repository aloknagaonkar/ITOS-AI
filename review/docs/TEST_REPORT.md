# Sprint 13 Test Report

Behavioural tests were added for the futures matrix, neutral/missing/proxy inputs, options premium confirmation, buying/writing/mixed states, liquidity, IV, Greeks, volume confirmation, malformed inputs, location context, confidence bounds, and decision neutrality.

**pytest not executed by Codex — local validation required.**

Local validation commands are `python -m pytest -q` and `streamlit run app.py`. UI validation was not executed by Codex.

## Sprint 13 corrective validation
Focused behavioural coverage now requires canonical `volume_structure`, preserves unavailable OI degradation, isolates premium availability by option side, verifies location bonuses for writing, rejects malformed premium evidence, and confirms recommendations remain unchanged. Pytest was not executed by Codex — local validation required.

## Typed-input boundary regression
Added focused behavioural coverage for explicit typed/legacy input-mode preservation, early typed dependency guarding, prevention of legacy fallback calls from typed input, legacy mapping parity, the complete futures matrix, independent options classification, and recommendation neutrality. Pytest not executed by Codex — local validation required.
