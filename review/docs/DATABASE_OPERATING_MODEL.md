# Database Operating Model

## Separate responsibilities

* **Operational SQLite** is the non-rebuildable authority for Live snapshots, audit, and trade lifecycle state.
* **Market Lake** is the authoritative, durable source for historical candles, expired-option candles, frozen intelligence, outcomes, manifests, and checkpoints.
* **Historical index SQLite** is a rebuildable derivative containing stable trade IDs, versioned fingerprints, outcome metadata, and candidate-search fields.

They remain separate because retention, authority, recovery, write cadence, and rebuild semantics differ. No cross-database transaction or merged schema is introduced.

## SQLite operation

Each historical-index connection enables `foreign_keys`, WAL journaling, a 5000 ms busy timeout, and NORMAL synchronous mode. Connections are short-lived and are never stored in Streamlit session state. Metadata records the schema version; diagnostics expose schema, configured fingerprint version, path, and `integrity_check` result.

Back up operational SQLite and the Market Lake as authoritative data. The historical index can be backed up for convenience but is recoverable by deleting a corrupt index and explicitly rebuilding it from the Market Lake. Schema mismatch requires an explicit migration/rebuild rather than silent mutation. PostgreSQL should be reconsidered only when measured concurrent-writer contention, data size, availability requirements, or multi-host deployment exceeds SQLite's operating envelope; it is not part of this sprint.

## Sprint 18.4F.2 run checkpoints
Token-free run checkpoint JSON is operational coordination metadata only. It does not merge Operational SQLite, the Market Lake source of truth, or rebuildable Historical Index SQLite, and no open connection is stored in Streamlit state.
