# Architecture Notes — Sprint 18.4E
`market_lake.HistoricalIntelligenceRecord.trade_id` is an additive property. `historical_intelligence_index.py` owns configuration, registries, contracts, builder, SQLite adapter, build service, statistics cache, and relationship graph so analytical engines remain index-unaware. SQLite uses a composite identity/version primary key, secondary filter indexes, transactional bulk writes, parameter binding, and a mutation generation for cache freshness.

Hardening centralizes nested field extraction in an explicit alias registry, persists canonical logical identity for collision checks, adds read-only structural validation/status, paginates complete cache computation, emits symmetric graph edges, and provides optional failure-isolated persistence hooks.
