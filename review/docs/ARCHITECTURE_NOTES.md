# Architecture Notes
`itos_platform.market_lake` supplies the storage protocol and dependency-free local implementation. Atomic typed JSON is used instead of unavailable Parquet support. Provider fetchers and existing pipeline runners are injected, preserving no-live-fallback and preventing a second decision formula. Intelligence is engine-version partitioned and outcomes are a distinct layer.
