# Historical Pipeline Integration Rules — Sprint 18.4F.1

The composition root owns one `LocalHistoricalMarketLake` and one `SQLiteHistoricalIntelligenceIndex` and injects them into analytics, synchronization, enrichment, outcomes, similarity, capture, finalization, and option services. Every build/download/finalize operation is initiated by an explicit UI action. Historical decisions read only Market Lake candles at or before the replay cutoff, invoke the existing application pipeline once, never fall back to Live data, and never place orders. Outcomes are factual, separately persisted future observations and never alter frozen decisions or fingerprints. OAuth clients remain process dependencies and tokens are never persisted in historical records or Streamlit state.

## Sprint 18.4F.2 guided boundary
Normal Historical Analysis now enters the existing pipeline through one explicit orchestrator call. Stage order, failure isolation, candle-only fallback, and automatic result preparation are defined in `HISTORICAL_ANALYSIS_ORCHESTRATOR.md`; formulas and persistence ownership are unchanged.
