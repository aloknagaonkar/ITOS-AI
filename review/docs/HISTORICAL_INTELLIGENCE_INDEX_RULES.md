# Historical Intelligence Index Rules — Sprint 18.4E

## Identity and architecture
Trade IDs canonically join provider, instrument key, underlying, interval, ISO analysis timestamp, engine version, and Market Lake intelligence schema version. SHA-256 supplies a configurable 20-hex-character suffix; the readable prefix contains underlying, time, and interval. Secrets and process-dependent `hash()` are excluded.

The additive flow is Market Lake record → identity → decision-time fingerprint → SQLite index → regenerable statistics cache → lightweight relationship graph. No analytical engine or `DecisionPipeline` is invoked.

## SQLite schema and queries
`historical_intelligence_index` has a composite `(trade_id, fingerprint_version)` key so versions coexist. Its identity, categorical, confidence, serialized tokens/features, separate outcome metadata, flags, and timestamps are indexed by the documented lookup dimensions. `index_metadata` prevents destructive schema mismatch; cache and generation tables support invalidation. Queries use bound parameters, an order allowlist, bounded limit/offset, deterministic tie-breaking, date/confidence ranges and ALL/ANY token filters.

## Incremental maintenance and rebuilds
Build-missing is default, transactional batches are idempotent, duplicate identities are reported, and a checkpoint records progress. Current rows are skipped. Outdated fingerprints rebuild only with `rebuild_outdated`; full rebuilding is explicit. Outcome refresh changes only separate metadata and invalidates statistics. Raw records are never rewritten and fingerprint creation never reruns decisions. Live/enrichment auto-update switches default off for safe integration.

## Versions, cache, and graph
Index, fingerprint, feature, semantic, and statistics versions are independent configuration. Existing fingerprint versions remain readable side by side. Statistics cache identity includes caller filter identity plus statistics version and refuses a generation-stale value. It reports distributions and confidence summaries, never “model accuracy.” The initial graph uses deterministic Jaccard token overlap, explicit opposite rules, overlap/neighbor limits, no self-links, and outcome labels only to classify a relationship after its decision-state score is calculated.

## Compatibility, security, and performance
Legacy Market Lake records derive identity and missing fields become `UNKNOWN`/`None` with flags; no fabricated directional evidence is introduced. OAuth tokens, headers, API keys, cookies, clients and provider objects are not persisted. SQLite is local, parameterized, indexed, paginated, transactional, and does not require loading Market Lake files for lookup. Generated databases/checkpoints are ignored. Final similarity scoring and Pattern Discovery are deferred to Sprint 18.4F.
