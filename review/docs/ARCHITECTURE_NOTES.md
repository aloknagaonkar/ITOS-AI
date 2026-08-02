# Architecture Notes

`UpstoxHistoricalSyncProvider` is an authentication-agnostic adapter over the existing client. `HistoricalSyncManager` owns planning, chunks, retries, partitioning, progress, and manifest checkpoints while delegating persistence/enrichment/outcomes to Market Lake services. Immutable plan/result/progress models cross the application boundary. Typed instrument and sync configuration centralize mappings and limits. Streamlit only composes authenticated runtime dependencies and invalidates its isolated Analytics namespace.
