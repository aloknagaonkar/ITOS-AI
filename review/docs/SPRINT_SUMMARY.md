# MarketSnapshot UI Integration Repair

The Streamlit presentation layer now reads instrument, expiry, timeframe, and refresh metadata directly from the `DashboardApplicationResult.market_snapshot`. Legacy `engine_underlying`, `engine_expiry`, `tracked_underlying`, `tracked_expiry`, `stored_underlying`, and `stored_expiry` references were removed from download filenames, chart titles, dashboard labels, history reads, and report persistence calls.

The application service also uses its canonical `MarketSnapshot` identity for all existing history operations. No trading logic, engine calculations, thresholds, recommendation behavior, dashboard layout, or persistence operations changed.
