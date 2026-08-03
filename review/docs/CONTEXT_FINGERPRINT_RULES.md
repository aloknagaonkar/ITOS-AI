# Context Fingerprint Rules — Sprint 18.4F

`context-v1` is separate from the decision-state fingerprint. It derives session phase (pre-open, opening, morning, midday, afternoon, closing, outside), normalized minutes from open/to close, weekday, expiry-day/days-to-expiry, gap direction/magnitude, volatility regime, trend/range and opening-range context, and previous-day location only when inputs exist.

Session bounds are 09:15–15:30 in the supplied timestamp's frozen clock. Gap uses opening price versus previous close with a documented flat band. Expiry and previous-day values remain unknown when unavailable. Unknown/missing values reduce coverage and do not match or become zero.

Only values supplied at the analysis timestamp are consumed. No end-of-day state or future candle is derived for an intraday source. Version changes are required for formula or semantic changes; incompatible context versions must not be silently reinterpreted.
