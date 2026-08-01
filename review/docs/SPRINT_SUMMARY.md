# Resilient Upstox Candle Acquisition

Candle acquisition now uses Upstox V3 intraday candles and falls back to a V3 historical range, selecting the latest trading day returned. Instrument keys are canonicalized to one URL-encoding pass, including `NSE_INDEX|Nifty 50`. Responses are normalized to typed DataFrames, and safe structured logs exclude authorization headers and tokens.

When neither source supplies usable candles, the application returns an explicit unavailable result, Data Health blocks trading, the recommendation is forced to WAIT, and Streamlit displays a clear warning without running candle-dependent calculations. Trading formulas, thresholds, safety gates, and normal engine order are unchanged.
