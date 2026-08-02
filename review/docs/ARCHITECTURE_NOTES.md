# Architecture Notes

`itos_platform.replay_ux` is framework-neutral and owns typed immutable outcome/timeline values, replay-prefixed session state, completed-candle resolution, safe reset, and statistics. `ui.replay_workspace` is a thin Streamlit adapter. Providers remain the sole owners of market data construction and ReplayMetadata. Future outcome data is passed through a separate `ReplayOutcome` path and never appended to `MarketSnapshot.historical_candles`. The live route remains the pre-existing application route.
