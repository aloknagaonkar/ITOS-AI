# Historical Trade Review Rules — Sprint 18.4D.2

## Trader-facing surfaces
Historical Analytics now presents visual date coverage, aggregate Analyst Dashboard modules, the filtered Historical Trade Review table, a selected frozen-record deep dive, historical-option coverage, collapsed Advanced Diagnostics, and Developer → Market Lake. Normal UI uses cards and tables; JSON appears only in the collapsed developer diagnostic expander.

## Directional evaluation
`FAVOURABLE`, `UNFAVOURABLE`, `INCONCLUSIVE`, `NOT_EVALUABLE`, `AVOIDED`, and `MISSED_OPPORTUNITY` compare a frozen BUY CE/BUY PE/WAIT recommendation with later factual underlying movement. Thresholds are configuration-owned. These labels are not win/loss, P&L, execution, or trade lifecycle claims. Actual trade success/failure remains deferred to Sprint 18.5.

## Trigger Checklist and reasons
Ten stored-evidence groups return immutable PASS, PARTIAL, FAIL, or UNAVAILABLE results, evidence, impact, missing requirement, fix, quality flags, and a stable target. Blocking summaries use FAIL, UNAVAILABLE, PARTIAL priority. Reasons come only from stored flags and factual outcomes; unsupported explanations are omitted. Missing option facts are never PASS.

## Deep links
Rows select immutable record IDs. Failed/partial/unavailable checks target the centralized registry (`market-structure`, `price-volume`, `positioning`, `compression`, manipulation and subtargets, `institutional-evidence`, `decision-confidence`, `decision-validation`, `trade-ranking`, `option-data-coverage`, `historical-outcome`). Back-to-table state uses only `historical_trade_review_*` keys.

## Options
The explicit downloader independently discovers expiries and expired CE/PE contracts and stores official expired-contract OHLC, volume, and OI candles. The derived chain aligns timestamp, expiry, strike, side, OHLC/LTP, volume, and OI. It is `PARTIAL_OPTION_REPLAY`, not an historical exchange chain snapshot. Historical bid/ask, IV, and Greeks remain unavailable and are never fabricated.

## Live capture and finalization
The scheduler-ready capture service applies cadence configuration, deterministic identity, safe serialization, idempotent writes, raw/intelligence/optional-option persistence, and failure isolation. Secret/token keys are excluded. Explicit finalization reads stored session records, builds factual outcomes, and reports incomplete until required future data exists; no order API is reachable.
