# Known Issues
- Typed JSON is the v1 fallback; a Parquet adapter can be added behind the protocol when a Parquet engine is approved.
- Exchange holiday discovery remains provider-driven; callers provide expected dates and no-data dates are recorded.
- Corrupt reads safely return unavailable, but physical quarantine/repair tooling is deferred.
- The runner adapter must be wired by deployment code to its configured HistoricalReplayProvider and DashboardApplicationService.
- Manifest intelligence/outcome completion updates are available as typed fields; orchestration-specific promotion occurs after the owning batch decides its date is complete.
