# Manipulation Rules

## Evidence, not intent
The engine reports **possible failed acceptance and trap behaviour**, never proof of deliberate manipulation. Scores are informational only and cannot modify recommendations.

## Event formulas
- **False breakout:** a completed high exceeds resistance by `breakout_minimum_distance`, a later completed close returns at/below resistance, and acceptance/follow-through are weak. A retest that holds above resistance is not false.
- **False breakdown:** the symmetric rule below support using `breakdown_minimum_distance`; support must be reclaimed.
- **Liquidity sweep:** failed breach plus rejection at or above `rejection_threshold`; side is above resistance, below support, both, or none.
- **Stop-hunt probability:** 35% rejection + 30 fast re-entry + 20 effort/result imbalance + 15 sweep evidence. It is an evidence score, not intent.
- **Wick/rejection:** wick score is the largest wick divided by total spread. Rejection adds range re-entry only at a meaningful breached level. Zero-width candles are unavailable.
- **Range re-entry:** candle distance counts from the last completed breach to the first completed close back inside; `fast_reentry_candle_window` defines fast.

## Quality models
- **Follow-through:** 60% fraction of completed closes outside the level + 25% maintained normalized distance + 15% supplied volume confirmation.
- **Breakout quality:** 45% acceptance + 35% follow-through + 20% volume, reduced by range re-entry and opposing wick.
- **Compression release:** releasing/high compression lowers risk for strong follow-through and raises risk only when an actual breach re-enters. Compression alone is never manipulation.
- **Positioning:** only confirms or contradicts an existing price event. Bullish positioning reduces bull-trap risk; bearish positioning reduces bear-trap risk.

## Probability and severity
Manipulation probability is the configured sum of range re-entry (24), failed move (18), wick/rejection (14), poor follow-through (14), effort/result (8), sweep (10), location (6), and legacy agreement (6), minus `contradiction_penalty` per contradiction. Bands are Low 0–24, Developing 25–44, Moderate 45–64, High 65–84, Very High 85–100.

Trap severity is separate: 30% rejection/distance, 25% reversal speed, 25% adverse follow-through, and 20% volume/effort context. Direction is `BEARISH_TRAP` after failed upside, `BULLISH_TRAP` after failed downside, neutral for both/unresolved, and unknown when unavailable.

## Configuration defaults
`breakout_minimum_distance=.001`, `breakdown_minimum_distance=.001`, `level_proximity_tolerance=.003`, `wick_ratio_threshold=.35`, `rejection_threshold=45`, `range_reentry_threshold=0`, fast re-entry 2 candles, follow-through 3 candles, minimum confirmation 2, minimum input 6 candles, volume expansion 1.25x, effort/result threshold .35, stop hunt 60, sweep 45, bull/bear trap 65, possible/moderate/high/confirmed 25/45/65/85, missing-data confidence ceiling 35, stale threshold 1800 seconds. All weights are fields in `ManipulationIntelligenceSettings`, not scattered literals.

## Quality flags and degradation
Supported flags include candle missing/insufficient, invalid OHLC, volume unavailable, support/resistance/range unavailable, market-location/volume/positioning/compression/legacy evidence unavailable, insufficient follow-through, stale data, unconfirmed manipulation, zero-width candle and conflicted direction. Critical candle/range failures return `UNAVAILABLE`; optional evidence lowers/caps confidence. Scores are clamped 0–100. Missing data never creates a BUY.
