# Simplified Historical Analysis UX — Sprint 18.4F.2

The normal workflow is deliberately date-only: select **Underlying**, **From Date**, and **To Date**, then explicitly click **Download & Analyze**. Nothing runs on page load. That single action plans the range and automatically downloads missing underlying candles and supported historical options, builds point-in-time intelligence and factual outcomes, updates the historical index, and prepares stored analytics.

## Progress and coverage

The UI renders a unified, monotonic progress bar, current stage/date, safe status message, and readable date rows. Weekends are `NOT_TRADING_SESSION` and skipped; option unavailability is partial/candle-only rather than a blocker. Completed work is checkpointed by stable run ID. Cancellation stops between atomic operations and retains checkpoints; a subsequent run can retry incomplete work without deleting successful source data.

## Results

Results open automatically and include coverage, directional setup/outcome summaries, the existing Historical Trade Review, Trigger Checklist diagnosis and deep dives. `MISSED_OPPORTUNITY` rows provide the deterministic missed-opportunity summary and remain analysis input for Sprint 18.4G. They do not alter live decisions. These are historical directional setup evaluations; actual trade win/loss requires defined entry, stop, target and exit rules.

## Developer controls

Provider/instrument details, cadence, rebuild flags, maintenance actions and diagnostics remain in **Advanced Developer Controls**, collapsed by default. Normal UI renders tables and metrics, never raw JSON. Sanitized raw diagnostics remain developer-only.
