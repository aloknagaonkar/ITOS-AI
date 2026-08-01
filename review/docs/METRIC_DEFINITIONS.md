# Institutional Metrics v2 Definitions

All metrics are observational in Sprint 9 and **none influences recommendations, confidence, strike selection, or safety gates**.

## Sources and normalization
`OptionChainSchemaAdapter` maps documented provider aliases to `strike`, side OI/OI-change, volume, IV, delta/gamma/theta/vega, LTP, bid/ask and price-change. Values are numeric-coerced. Missing columns create `missing_<concept>`; invalid cells create `malformed_<concept>`. Missing evidence is `None` (ratios/derived measures) or zero only for factual totals, never directional evidence.

## Formulas
- **OI:** sums of each side's OI and OI change. ATM-window OI sums the nearest spot strike plus `atm_window` rows each side.
- **Velocity:** `(OI[t]-OI[t-1])/elapsed_seconds * velocity_interval_seconds`. **Acceleration:** `(velocity[t]-velocity[t-1])/elapsed_seconds * velocity_interval_seconds`. Requires `minimum_history_length` timestamped compatible observations; otherwise `insufficient_oi_history` and `None`.
- **PCR:** `put_oi/call_oi`, `put_oi_change/call_oi_change`, and `put_volume/call_volume`. A zero denominator returns `None` and `pcr_denominator_unavailable`. Negative change values retain their signs. Weighted PCR is the renormalized available-component weighted mean using `weighted_pcr_*_weight` (defaults .50/.25/.25); absent components are not synthesized.
- **Max Pain:** for each available strike S, `sum(max(S-K,0)*call_OI + max(K-S,0)*put_OI)`; returns the first minimum-payout strike. Requires strike and both OIs; otherwise `max_pain_unavailable`.
- **IV:** arithmetic side averages; ATM IV is the average of available side IVs in the configured ATM window; skew is `put_IV-call_IV`. Percentile is `100 * count(history_IV <= current_ATM_IV)/count(history_IV)` over `iv_percentile_lookback`, requiring minimum history, else `insufficient_iv_history`.
- **Greeks:** each side Greek is weighted by absolute side OI (or volume when `greek_weighting=volume`): `sum(greek*abs(weight))/sum(abs(weight))`. Combined gamma/theta/vega average available side aggregates. Gamma exposure is `sum(gamma*OI)`; net is call exposure minus put exposure. Greek signs are preserved. Missing inputs create `incomplete_greeks`.
- **Liquidity:** volume totals are sums. Per-quote spread ratio is `(ask-bid)/midpoint`; quality linearly maps `good_spread_ratio` to 100 and `poor_spread_ratio` to 0, clipped. Liquidity score is the mean of quote quality and volume score `min(100,total_volume/liquid_market_volume*100)`; without quotes it uses volume alone, while missing volume forces zero. Thin market is `total_volume < thin_market_volume`. Flags: `missing_bid_ask`, `incomplete_volume`.
- **Positioning:** existing price/OI quadrants: price+/OI+ long buildup; price-/OI+ short buildup/writing; price-/OI- long unwinding; price+/OI- short covering. Scores sum absolute OI change. Call/put writing are their respective short-build-up totals. Dominant state is the largest evidence total. Direction remains neutral in this foundation.
- **Futures premium:** normalized from an existing summary value only; no synthetic calculation.

## Configuration defaults
`atm_window=1`, PCR weights `.50/.25/.25`, spread thresholds `.02/.10`, thin/liquid volume `1000/10000`, history minimum `3`, velocity interval `60s`, IV lookback `20`, Greek weighting `oi`. Overrides live under `runtime_configuration["institutional_metrics"]`.

## Assumptions and quality
Rows refer to one compatible instrument/expiry. Historical frames contain `timestamp`, `call_oi`, `put_oi`, and optionally `atm_iv`. Empty chains produce `empty_option_chain`, safe empty contracts, and no directional classification.
