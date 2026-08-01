# ITOS v9.2.1 — Institutional Intelligence Drop 1

## Added
- Production `InstitutionalConfidenceEngine` with weighted OI, PCR, volume, VWAP, Greeks, max-pain, trend and futures evidence.
- `StrikeRanker` with liquidity, spread, delta, OI, volume, IV and ATM proximity scoring.
- `AIOrchestrator` that isolates engine failures, combines directional votes and produces dashboard-ready recommendations.
- Backward-compatible confidence and strike-ranking helper functions.
- Smoke tests for confidence, ranking and orchestration.

## Changed
- `EngineResult` now supports calibrated confidence and per-engine weight while preserving the original positional constructor.

## Safety
- Missing data is treated as neutral and reduces completeness.
- One engine failure no longer crashes the entire orchestrator.
- Wide-spread and missing-LTP contracts receive ranking penalties.
