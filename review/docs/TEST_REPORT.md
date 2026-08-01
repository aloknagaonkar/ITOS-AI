# Validation Report — Resilient Upstox Candle Acquisition

Validation follows the requested Codex scope: Python compilation and whitespace/error checking only. Pytest was intentionally not run.

Added automated coverage for V3 intraday success, historical fallback, empty sources, malformed payloads/rows, invalid instruments, exactly-once NIFTY key encoding, safe logging, and downstream WAIT/data-health blocking.
