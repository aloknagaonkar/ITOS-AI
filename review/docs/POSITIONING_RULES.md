# Positioning Intelligence Rules

## Futures matrix
| Price | Futures OI | State | Meaning | Likely impact |
|---|---|---|---|---|
| Rising | Rising | Long Build-up | New buyers are entering | Fresh bullish positions may sustain with confirmation |
| Falling | Rising | Short Build-up | New sellers are entering | Downside may continue with confirmation |
| Rising | Falling | Short Covering | Existing shorts are exiting | A sharp rally may need fresh longs to sustain |
| Falling | Falling | Long Unwinding | Existing longs are exiting | Weakness is not necessarily fresh short selling |

Price and OI use configurable neutral bands. Missing OI is unavailable; explicitly labelled aggregate option OI may only be used as a flagged, confidence-capped proxy.

## Options writing and buying
OI increase alone never selects a state. Put/call writing requires rising respective OI, stable/falling premium, and the existing writing score. Call/put buying requires rising premium and demand volume. Similar competing signals return Mixed. Put writing means possible conditional support; call writing means possible conditional resistance. Call buying may be directional or hedging; put buying may be bearish demand or protection.

## Confirmation
Premium confirmation is mandatory for a directional options state. IV is contextual and missing IV is flagged rather than invented. Volume confirmation adds futures confidence; divergence subtracts it. Liquidity and location can strengthen or weaken interpretation. Greeks, IV, liquidity, Market Location, and Volume Structure omissions have explicit flags.

## Confidence model
Defaults live in `PositioningIntelligenceSettings`: price/OI 45, volume 15, premium 20, liquidity 10, context 10, conflict penalty 25, missing-data ceiling 40, and proxy ceiling 55. Every output is clamped to 0–100. Configuration may override neutral thresholds, minimum OI/volume, writing/buying thresholds, premium/IV thresholds, liquidity, weights, penalties, ceilings, and stale threshold.

## Conflict and quality handling
Contradictory directional votes produce `CONFLICTED`; competing options signals produce `MIXED` and `POSITIONING_CONFLICTED`. Quality flags include price/OI/history/proxy, premium, IV, Greeks, liquidity, location, volume structure, conflict, and stale-data conditions as applicable. Malformed or missing data safely returns Unavailable/Neutral/Mixed with low confidence.

## Human explanations and safe degradation
Every state separates measured evidence from cautious interpretation and provides its human meaning and conditional market impact. No guarantee is expressed. The output is informational only and cannot promote BUY CE/PE, modify WAIT, or affect safety, confidence, strikes, planning, or execution.

## Canonical dependency and premium-side rules
A typed `DecisionContext` requires `VolumeStructure` before futures positioning can be inferred; when it is absent, futures positioning is unavailable and snapshot intelligence is not used to reconstruct direction. True or explicitly labelled proxy OI is also required. Options premium availability is side-specific: `CALL_PREMIUM_UNAVAILABLE` affects only call states and `PUT_PREMIUM_UNAVAILABLE` affects only put states. Missing opposite-side premium remains a quality disclosure but does not impose the selected state's missing-data ceiling.
