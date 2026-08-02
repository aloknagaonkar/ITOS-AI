# Architecture Notes
All modes converge at immutable `MarketSnapshot`. Providers alone acquire and
normalize data. Replay filters candles/options before pipeline entry and the
application service filters persisted histories. The default service path remains live.
