# Known Issues

- Historical option-chain snapshots are unavailable through this candle sync; records are `CANDLE_ONLY_REPLAY`.
- Intelligence action availability depends on deployment injection of the existing point-in-time replay runner.
- Exchange holidays are learned from provider responses/manifest; preview weekday counts are candidates, not fabricated sessions.
- No background worker is provided; synchronization is sequential and UI cancellation takes effect at safe checkpoints.
- Pytest and interactive UI validation were not run; local validation is required.
