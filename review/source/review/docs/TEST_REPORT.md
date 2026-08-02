# Test Report

Codex validation is intentionally limited by sprint instruction to Python compilation and `git diff --check`. Pytest was **not run**; local validation with `python -m pytest -q` is required. Streamlit UI validation was **not run**; local validation with `streamlit run app.py` is required.

Deterministic compression tests cover missing/malformed/insufficient candles, zero ranges, score bounds, optional volume/OI degradation, compression/release behavior, typed/legacy parity, input immutability, DecisionContext reconciliation, and recommendation isolation. Full pipeline compatibility remains subject to local pytest validation.
