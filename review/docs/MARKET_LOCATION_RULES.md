# Market Location Rules — Sprint 11

## Active range
The engine selects one deterministic active range in this order: (1) a complete, numeric validated support/resistance pair from intelligence or option summary; (2) the extrema of the interior candles in the configured recent-swing lookback; (3) rolling candle extrema. A partial validated pair is not mixed with fallback evidence.

`range_position = clamp((current_price - active_low) / (active_high - active_low), 0, 1)` and `location_score = range_position * 100`.

## Zones
Defaults are configuration-driven: **BOTTOM** ≤15; **LOWER_RANGE** >15 and ≤35; **MIDDLE** >35 and <65; **UPPER_RANGE** ≥65 and <85; **TOP** ≥85. Confirmed breaks override these with **BREAKOUT_ZONE** and retests with **RETEST_ZONE**.

## Transitions
**MOVING_UP/DOWN** use the configured multi-close slope without a confirmed boundary break. **BREAKING_UP/DOWN** require the configured number of closes beyond resistance/support and displacement beyond the greater of the ATR and percentage thresholds. **RETESTING_UP** follows an upside break, returns within configured ATR tolerance, and remains at/above the level; **RETESTING_DOWN** is symmetric below support. **FAILED_BREAKOUT/BREAKDOWN** occurs when a prior close exceeded the level and price returns inside within the configured failure window. **STABLE** means the slope/break evidence is unconfirmed.

## Safe degradation and flags
Missing candles, insufficient candles, missing OHLC, malformed numerics, unavailable ranges, and zero-width ranges return UNKNOWN, neutral/unknown direction, low confidence, and a display-only score of 50. Flags include `CANDLES_MISSING`, `CANDLES_INSUFFICIENT`, `OHLC_INVALID`, `ACTIVE_RANGE_UNAVAILABLE`, `ZERO_WIDTH_RANGE`, `SUPPORT_UNAVAILABLE`, `RESISTANCE_UNAVAILABLE`, `ATR_UNAVAILABLE`, `TRANSITION_UNCONFIRMED`, `STALE_DATA`, and reserved `CONFLICTING_STRUCTURE`. Missing ATR uses candle true range while retaining `ATR_UNAVAILABLE`.

## Interpretation boundary
Middle-zone motion can be rotation, expansion, or trend initiation. It is deliberately **not** accumulation or distribution: those labels require future volume-structure and institutional-evidence engines. Market location is informational only in Sprint 11 and cannot promote or alter BUY CE, BUY PE, or WAIT.
