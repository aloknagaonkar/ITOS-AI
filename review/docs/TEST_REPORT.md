# Test Report

pytest not executed by Codex — local validation required.

Deterministic behavioural contracts were added for state bands, individual components, OI availability/proxy handling, release direction, expansion, directional alignment/conflict, malformed and missing inputs, score bounds, dashboard-facing fields, dependency flags, and informational-only recommendation preservation. Local validation commands are `python -m pytest -q` and `streamlit run app.py`.

The Sprint 14 local-validation follow-up isolates configured state classification at boundary-adjacent and exact-threshold scores. Separate composite coverage now verifies monotonic score growth across progressively tighter structures while zero-weighting unrelated test components. The malformed numeric fixture explicitly uses object dtype before inserting a string, then verifies safe coercion, bounded scores, and recommendation immutability.

The reported prior local result was **5 failed, 309 passed**. Pytest was not rerun by Codex; local validation is still required.
