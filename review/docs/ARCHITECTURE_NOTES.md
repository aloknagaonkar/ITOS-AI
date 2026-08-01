# Architecture Notes

The engine accepts either the canonical `DecisionContext` or a legacy mapping adapted once to `MarketSnapshot`. It reads only snapshot/configuration data, returns an immutable value object, and performs no persistence, Streamlit access, mutation, or recommendation work. Pipeline placement is after market-cycle, pattern, candle-DNA, smart-candlestick, and structure analysis. Downstream/application consumers receive the identical object stored under `engine_results["market_location"]` and `DecisionContext.market_location`.
