# Compression Intelligence Rules

## Compression versus consolidation
Consolidation only describes limited net travel. Compression requires agreement among sustained ATR, candle spread, multi-candle range, and return-volatility contraction; volume, duration, and OI are supporting rather than mandatory evidence.

## Formulas
All ratios use completed candles and return unavailable rather than zero when their baseline is absent or non-positive.

- **ATR:** true range is `max(high-low, |high-previous close|, |low-previous close|)`; `ATR ratio = mean(recent TR) / mean(baseline TR)`.
- **Candle spread:** `spread = high-low`; `spread ratio = mean(recent spread) / mean(baseline spread)`.
- **Rolling range:** `range = max(high)-min(low)`; `range ratio = recent-window range / baseline-window range`.
- **Volume:** `relative volume = mean(recent volume) / mean(baseline volume)`. Missing volume does not erase price compression.
- **Volatility:** standard deviation of close-to-close percentage returns; recent volatility is compared with its longer price-volatility baseline. Option IV is not blended with price volatility.
- **Time:** trailing closes inside the active recent high/low range are counted. The score reaches 100 at twice the configured minimum duration.
- **OI build-up:** positive futures OI change is normalized against the threshold. OI is optional, cannot determine direction, and proxy use is flagged and confidence-capped.
- **Component score:** for a valid contraction ratio `r`, `clamp((1-r)×200, 0, 100)`. Compression is the available-component weighted mean.
- **Energy stored:** `65% compression + 20% time + 15% OI`; unavailable OI contributes no positive energy.
- **Expansion readiness:** `35% compression + 30% energy + up to 35% release evidence`. It is not a probability.

## States and release
Default score bands are 0–24 No Compression, 25–44 Early, 45–64 Moderate, 65–84 High, and 85–100 Extreme. A materially widening latest spread or BREAKING_UP/BREAKING_DOWN transition can label a qualifying compressed structure **RELEASING**. Strong widening plus a boundary transition is **EXPANDING**. These labels do not validate authenticity; manipulation validation is deferred.

## Direction rules
Compression is direction-neutral. OI build-up never supplies direction. A BULLISH_LEAN or BEARISH_LEAN requires at least two agreeing existing Positioning, Volume Structure, or Market Location signals. One-sided evidence or conflict returns UNCONFIRMED; absent evidence returns UNKNOWN. A lean is informational only.

## Quality and missing data
Flags include `CANDLES_MISSING`, `CANDLES_INSUFFICIENT`, `OHLC_INVALID`, `ATR_UNAVAILABLE`, `ZERO_BASELINE_ATR`, `RANGE_UNAVAILABLE`, `ZERO_WIDTH_RANGE`, `VOLUME_UNAVAILABLE`, `VOLATILITY_UNAVAILABLE`, `OI_UNAVAILABLE`, `OI_PROXY_ONLY`, dependency-unavailable flags, `STALE_DATA`, `INVALID_TIMESTAMP`, `COMPONENTS_CONFLICTED`, and `COMPRESSION_UNCONFIRMED`. Missing critical candle data returns UNAVAILABLE, zero scores, low confidence, explanations, and no recommendation effect. Optional missing evidence remains `None`.

## Default configuration
Recent/baseline windows: ATR 5/20, spread 5/20, range 8/24, volume 5/20; volatility lookback 20; minimum candles 24. Component weights: ATR 20, range 20, spread 15, volume 10, volatility 15, time 15, OI 5. Minimum time duration 5, OI threshold 1, release/expansion ratios 1.25/1.50. Agreement/data confidence weights are 70/30, contradiction penalty 20, critical-missing ceiling 45, proxy-OI ceiling 55, and stale threshold 1,800 seconds. All values can be overridden under `compression_intelligence` in the existing context configuration mapping.

## Status
Sprint 14 is informational only. Compression cannot change CE/PE/WAIT, existing confidence, SafetyGatePolicy, AI Trade Opportunity, strike selection, trade plans, or execution.

## Behavioural validation boundaries
State-band validation supplies scores directly to the configured classifier so unrelated composite inputs cannot distort threshold assertions. Exact defaults are inclusive at 25 (Early), 45 (Moderate), 65 (High), and 85 (Extreme), with the immediately lower score remaining in the preceding band. Composite behaviour is validated separately by progressively tightening recent candles while explicitly assigning zero test weight to volume, return volatility, time, and OI; this preserves meaningful ATR, rolling-range, and candle-spread interaction without claiming that candle scale alone determines a final state. Intentional non-numeric candle fixtures use object dtype before inserting malformed content so safe production coercion is actually exercised.
