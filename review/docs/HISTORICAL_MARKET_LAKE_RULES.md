# Historical Market Lake Rules — Sprint 18.4C

## Architecture and layout
The lake has three strictly separated layers: immutable raw source records, point-in-time ITOS intelligence, and factual future outcomes. Normalized candles are a reusable derivative of raw data. Local storage is partitioned by provider/instrument/interval/date under `data/market_lake`; options additionally partition by expiry and intelligence/outcomes by engine version. Typed, atomic JSON is the documented fallback because the repository has no Parquet engine dependency.

## Raw immutability, requests, and manifests
`HistoricalRangeRequest` is immutable and validates ordering, future dates, interval, instrument, enablement, and maximum range. No live fallback exists. Raw writes normalize a defensive copy and retain absent volume/option values as missing. Atomic manifests record schemas, engine/cadence, completed/incomplete/failed/no-data/option dates, record counts, timestamps, flags, and explanations. Completion is recorded only after storage succeeds.

## Schema and engine versions
Raw, intelligence, and outcome schema versions are explicit. Intelligence and outcomes are stored side-by-side by engine version; raw partitions remain reusable. Engine changes never silently overwrite prior intelligence. Controlled rebuild flags allow each layer to be reconsidered independently.

## Incremental ingestion
Sync compares expected sessions with manifest completion, fetches only missing/incomplete or explicitly rebuilt dates, validates and stores each date atomically, continues after per-date failures, and reports completed/skipped/failed/no-data dates. Provider no-data responses are not fabricated as trading sessions.

## Point-in-time enrichment and resume
Each configured cadence point creates a fresh `ReplayRequest` and invokes an injected runner for the existing replay/dashboard pipeline. The cutoff is checked before storage; a later completed candle raises `NO_LOOK_AHEAD_VIOLATION` and the point is not written. Deterministic record identity and checkpoint upserts permit restart and skip completed points. Mutable recommendation/context objects are not shared by this service.

## Options
Option snapshots preserve null bid/ask/OI/volume/IV/Greeks and partition by expiry. Replay completeness and actual ranking quality are serialized; missing options are never invented and existing blocking/degradation rules remain authoritative.

## Outcomes
Outcome enrichment is a separate pass over already frozen intelligence. It stores reference and horizon prices, point/percentage movement, session close, MFE/MAE, availability, and quality flags. Outcomes are linked by intelligence identity and never enter the decision runner. No success/win label is inferred.

MFE is the maximum upward underlying-price excursion from the frozen reference price through the remainder of that historical trading session. The analysis candle and every candle at or before the frozen cutoff are excluded. This is currently a direction-neutral underlying excursion, not a CE/PE trade-profit calculation. Direction-aware trade MFE/MAE belongs to a later Historical Analytics or Execution Decision release.

## Query and availability contracts
The typed query supports date/time, instrument, interval, recommendation, bias, positioning, compression, manipulation, confidence, ranking eligibility, replay completeness, engine version, and quality flags, with partition pruning and defensive results. Availability reports raw/intelligence/outcome/option coverage, missing dates, clamped completeness, flags, and explanations. Aggregate Historical Analytics are deferred.

## Security, rebuilds, and hygiene
`data/market_lake/` is Git-ignored. Tokens, secrets, authorization headers, API keys, and account identifiers are removed from serialized nested metadata; none appear in paths/cache keys/manifests. Atomic replacement prevents partial files from appearing complete, and corrupt files degrade to unavailable according to the quarantine-and-report policy (physical quarantine remains future hardening).

Generic typed storage and dashboard-result sanitization use separate policies. A provider identity such as `provider: archive` is valid persistent dataset metadata and is preserved in manifests and intelligence records. Runtime provider/client objects, `market_snapshot`, and extracted `replay_metadata` are excluded only while sanitizing dashboard results. Private and secret-like fields are redacted in every serialization context.

## Explicit deferrals
Sprint 18.4D will build Historical Analytics. Sprint 18.4E will build Similarity and Pattern Discovery. The Execution Decision Engine follows historical intelligence. None of those engines or dashboards is implemented here.
