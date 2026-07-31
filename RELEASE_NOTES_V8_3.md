# ITOS v8.3 — Enterprise Foundation & Data Health

This additive release starts the enterprise architecture upgrade on top of v8.2.1.

## Added

- Broker/data-source neutral `DataProvider` contract.
- Standard `MarketDataEnvelope` and `ProviderHealth` runtime models.
- Data Health Engine validating option-chain availability, core intelligence completeness, recommendation availability and refresh freshness.
- Dashboard Data Layer Health card with explicit HEALTHY, DEGRADED, STALE/INCOMPLETE and TRADING DISABLED states.
- Safety warning when decision inputs are not reliable enough for trading.

## Preserved

All v8.2.1 decision intelligence, historical intelligence, institutional engines, replay, confidence, trade planning and paper-tracking capabilities remain unchanged.

## Next enterprise milestone

- Unified provider adapters for Upstox, TradingView-compatible webhook ingestion and historical storage.
- Liquidity Map and Trade Health engines.
- Shared Market State object for all intelligence engines.
