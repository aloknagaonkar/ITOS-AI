# Files Changed — Resilient Upstox Candle Acquisition

| Filename | Reason changed |
|---|---|
| `upstox_client.py` | Use the V3 intraday route, canonicalize instrument encoding, safely log responses, normalize malformed data, and fall back to the latest historical trading day. |
| `dashboard_application_service.py` | Return a typed unavailable dashboard result that blocks trading when both candle sources are empty. |
| `engines/data_health_engine.py` | Treat missing candle history as unhealthy and trading-blocking. |
| `app.py` | Display the candle-unavailable warning and stop before rendering unavailable analysis. |
| `tests/test_upstox_client.py` | Cover V3 success, fallback, empty/malformed/error responses, and encoding. |
| `tests/test_dashboard_application_service.py` | Cover downstream WAIT and unhealthy data when candles are unavailable. |
| `review/source/*` | Refresh review copies of every modified production and test source file. |
| `review/docs/*` | Record implementation scope and validation. |
