# Positioning Intelligence Rules v1

## Futures positioning matrix

| Validated price | Explicit futures OI | State | Meaning |
|---|---|---|---|
| Rising | Rising | LONG_BUILDUP | New buyers are entering the market. |
| Falling | Rising | SHORT_BUILDUP | New sellers are entering the market. |
| Rising | Falling | SHORT_COVERING | Existing short sellers are exiting. |
| Falling | Falling | LONG_UNWINDING | Existing buyers are exiting. |

Configured neutral bands are 0.10% for price and 0.10/minimum 1.0 for OI. A neutral leg produces NEUTRAL. Missing OI produces UNAVAILABLE. Options OI is never silently treated as futures OI; an explicit proxy is flagged and capped at 55% confidence.

## Options writing and buying

Writing requires rising side OI, falling premium beyond 0.05, and the existing side writing score at or above 20. Put writing represents possible conditional support; call writing represents possible conditional resistance. Buying requires rising OI/demand, premium above 0.05, and side volume at or above 20. Call buying can be bullish demand or hedging; put buying can be bearish demand or protection. OI growth alone is not enough.

## Confirmation and confidence

The conservative defaults weight price/OI agreement 45, volume 15, premium 20, liquidity 10, and location/context 10. Confirming volume strengthens futures confidence; divergence weakens it. Premium is mandatory for an options writing/buying interpretation. IV (0.10 confirmation threshold), Greeks, liquidity (minimum score 25), location, and volume availability are surfaced as quality context. Bottom/put-writing and top/call-writing consistency add context confidence. Conflict subtracts 25. Missing critical data caps confidence at 45; proxy futures evidence caps it at 55. Every value is clamped to 0–100.

## Conflicts and quality flags

Comparable buying/writing behaviours or bullish/bearish disagreement produce MIXED/CONFLICTED rather than a forced direction. Flags include `PRICE_DIRECTION_UNAVAILABLE`, `OI_UNAVAILABLE`, `OI_HISTORY_INSUFFICIENT`, `FUTURES_OI_PROXY_ONLY`, `OPTION_PREMIUM_UNAVAILABLE`, `IV_UNAVAILABLE`, `GREEKS_UNAVAILABLE`, `LIQUIDITY_THIN`, `MARKET_LOCATION_UNAVAILABLE`, `VOLUME_STRUCTURE_UNAVAILABLE`, `POSITIONING_CONFLICTED`, and `STALE_DATA` (default threshold 1,800 seconds).

## Human meanings and market impact

Each state carries the requested cautious human meaning and impact: fresh longs may be more sustainable with confirmation; fresh shorts may extend downside; covering rallies may need fresh longs; long unwinding is not fresh short selling; writing creates only possible conditional support/resistance; buying may be directional or hedging/protection. No outcome is guaranteed.

## Safe degradation and status

Malformed chains, missing metrics, missing price/OI/premium/IV/Greeks/liquidity/location/volume, zero denominators, conflicts, and stale timestamps yield UNAVAILABLE, NEUTRAL, or MIXED with low confidence and explanations. Positioning Intelligence v1 is informational only and cannot create or promote BUY CE/BUY PE, alter WAIT, or bypass any safety or planning control.
