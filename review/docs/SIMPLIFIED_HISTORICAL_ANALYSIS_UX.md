# Simplified Historical Analysis UX — Hardened Sprint 18.4F.2

Normal users select only **Underlying**, **From Date**, and **To Date**, then explicitly click **Download & Analyze**. Nothing runs during page load. The one action plans dates, downloads missing underlying and supported option candles, builds point-in-time intelligence at the selected cadence, calculates factual outcomes, updates the shared historical index, and prepares stored analytics.

A single reusable Streamlit placeholder renders one progress bar, stage summary, current safe message, and date-level table. Rows distinguish Existing, Downloaded, Provider No Data, Not Trading Session, Partial Options, Options Unavailable, Intelligence Complete/Failed, Outcomes Complete/Pending/Not Evaluable, Indexed/Index Pending/Index Failed, Ready, Candle-only, Similarity unavailable, Partial and Retry Required. Results stay visible automatically.

Interactive cancellation is not shown because synchronous Streamlit execution cannot accept the click reliably. Programmatic cancellation remains available for future chunked/background execution. **Retry Failed Dates** reloads the stable checkpoint and repeats incomplete work only. **Retry Index Only** never downloads raw data or rebuilds intelligence/outcomes. Successful data remains stored across cancellation, failures and process restart.

Historical Trade Review, Trigger Checklist diagnosis, Similar Trades, Replay, and deterministic `MISSED_OPPORTUNITY` classifications remain unchanged. Advanced Developer Controls and sanitized diagnostics are collapsed by default. Normal UI contains no raw JSON.
