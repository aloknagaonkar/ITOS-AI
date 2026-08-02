# Historical Analytics Rules — Sprint 18.4D

## Boundary
Historical Analytics is a read-only consumer of persisted `HistoricalIntelligenceRecord` and `HistoricalOutcomeRecord` data. Analyze never calls Upstox, a replay provider, ingestion, enrichment, the Decision Pipeline, or any download function. Missing dates remain visible and no intelligence is fabricated.

## Requests and periods
Requests are immutable and include instrument, underlying, inclusive date range, interval, optional engine version, and all supported filters. WEEK, MONTH, THREE_MONTHS, SIX_MONTHS, and ONE_YEAR use the Market Lake period resolver; CUSTOM requires explicit valid start and end dates.

## Aggregation
All counts and statistics are deterministic over the currently filtered stored records. Outcomes report factual point movement at 5, 15, and 30 minutes, end of session, MFE, and MAE. They are never described as win rate or accuracy. Empty and incomplete ranges degrade to typed empty results and quality explanations.

## Isolation and safety
The workspace uses only `historical_analytics_*` session keys. It does not update live globals, replay state, recommendations, or CE/PE/WAIT logic. Export is built only from sanitized drill-down rows and associated stored factual outcomes.

## Maintenance
Developer → Market Lake is collapsed by default. Its buttons invoke deployment-provided callbacks to existing Market Lake ingestion, enrichment, and outcome services; Analyze never invokes those callbacks automatically.
