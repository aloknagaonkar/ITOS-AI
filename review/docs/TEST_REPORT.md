# Test Report
pytest not executed by Codex — local validation required.

Behavioural tests cover complete/empty/malformed chains, denominators, negative OI changes, optional IV/Greeks/volume/quotes, thin liquidity, deterministic PCR/Max Pain, Greek signs, IV skew, history velocity/acceleration/percentile, neutral malformed data, and preview fields. Pipeline identity and dashboard characterization remain covered by the existing suite and Sprint 9 additions. Run locally: `python -m pytest -q`.
