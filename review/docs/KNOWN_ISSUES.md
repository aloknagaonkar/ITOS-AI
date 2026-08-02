# Known Issues — Sprint 18.4D

- Expected trading sessions use weekdays because the existing Market Lake contract does not persist an exchange holiday calendar; manifest dates remain authoritative for actual coverage.
- JSON is the dependency-free secondary export. Parquet remains unavailable unless a supported Parquet engine is added to approved dependencies.
- Developer maintenance buttons require deployment wiring to existing ingestion/enrichment/outcome service callbacks and remain disabled when those callbacks are not configured.
- Historical aggregates reflect only fields persisted by the engine/schema version selected; unavailable facts are not synthesized.
