# Upstox Historical Sync Rules — Sprint 18.4D.1

## Authentication and security
The sync adapter receives the exact OAuth-authenticated Live `UpstoxClient` by dependency injection. It creates no client, performs no second login, never reads Streamlit state, and never persists, logs, places in a URL/cache key/manifest, or serializes the token or runtime client/provider. Authentication failures are always presented as **Historical Upstox authentication failed.** No raw headers or provider exception text is exposed. There is no Live/intraday/option-chain fallback.

## Instruments and endpoint
Typed instrument configuration maps NIFTY to `NSE_INDEX|Nifty 50` and BANKNIFTY to `NSE_INDEX|Nifty Bank`, with exchange, intervals, display name, and source. Overrides support future instruments. The adapter exclusively calls the existing authenticated client's Historical Candle V3 method.

## Planning, chunking, and normalization
WEEK, MONTH, THREE_MONTHS, SIX_MONTHS, ONE_YEAR, and CUSTOM resolve to bounded dates and weekday candidates; provider data and the manifest, not a fabricated calendar, establish actual sessions. The immutable preview reports complete, missing, incomplete, failed, enrichment/outcome work, versions, requests, and estimated cadence points. Configuration controls interval-specific chunk limits. Chunks are bounded, non-overlapping, and partitioned by Asia/Kolkata trading date. Normalization sorts ascending, deterministically removes duplicates, coerces numerics, rejects invalid OHLC/timestamps, preserves absent volume/OI as missing, and uses defensive copies.

## Missing-date synchronization
The manager reloads the manifest, skips complete dates unless explicit re-download is selected, requests only missing/incomplete ranges, partitions and validates each response, atomically stores each successful date through `LocalHistoricalMarketLake`, and checkpoints its manifest only after storage. Empty, malformed, mismatched, or failed partitions are never complete. Failed dates remain retryable; completed dates survive interruption and are skipped on resume.

## Independent actions
**Sync Missing Raw Data** alone calls Upstox and never runs `DecisionPipeline`. **Build Intelligence** reads stored raw data and invokes the existing point-in-time enrichment pipeline without Upstox. **Build Outcomes** reads stored raw/frozen intelligence and invokes factual outcome calculation without Upstox or `DecisionPipeline`. Re-download/rebuild toggles default false; versioned intelligence is not silently deleted.

## Retry, progress, checkpoint, and cancellation
Retries are finite and configuration-driven. Authentication errors are not retried blindly; timeout and rate-limit paths use conservative configurable delays. Progress exposes phase, date, chunk, rows, analysis points/outcomes, complete/skipped/failed counts. Cancellation is checked between chunks/dates and leaves prior atomic files and checkpoints intact.

## Option limitation and pilot
Ordinary historical candles do not contain historical option-chain snapshots. Option inclusion is disabled and records are classified `CANDLE_ONLY_REPLAY`; bid, ask, spread, Greeks, IV, and strike OI are never fabricated. Begin with the recommended NIFTY, one-minute, one-week, five-minute-cadence pilot.

## Market Lake and Analytics refresh
The manager reuses Market Lake request, manifest, local storage, enrichment, and outcome services. Raw/intelligence/outcome actions are separate. After mutation, only `historical_analytics_*` result/availability cache entries are invalidated. Analytics remains stored-data-only and runs only after the user clicks **Analyze Stored Data**; Live and Replay state are untouched.
