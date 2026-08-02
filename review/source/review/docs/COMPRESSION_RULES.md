# Compression Rules

## Current-architecture restoration

The immutable engine runs after typed location, volume, positioning, and institutional metrics and before manipulation. It is informational only and cannot create or alter BUY CE, BUY PE, or WAIT.

## Component formulas

- **ATR:** true range is `max(high-low, |high-previous close|, |low-previous close|)`. Recent mean TR is divided by longer-baseline mean TR. A zero baseline is invalid.
- **Spread:** the outlier-resistant median `high-low` over the recent window is compared with the longer median baseline.
- **Rolling range:** multi-candle recent `max(high)-min(low)` is compared with a longer multi-candle range, adjusted for configured window widths. Zero-width ranges are invalid.
- **Volume:** recent mean volume / baseline mean volume supports compression below one. Missing volume is not zero. Typed absorption contradicts simple volume contraction.
- **Volatility:** population standard deviation of close-to-close percentage returns over recent and baseline windows is compared. Option IV is not substituted.
- **Time:** containment percentage of baseline-window closes in the active recent range and consecutive contained duration measure persistence.
- **OI:** typed call/put OI velocity supports build-up. OI is optional, absent OI is not zero, and explicit proxy use is flagged/capped. OI never determines direction.

## Composite interpretation

Compression score is the normalized configured-weight average of available components. Energy stored separately combines compression, persistence, OI, and component agreement. Expansion readiness separately requires turning ATR/spread, boundary exit, volume increase, or follow-through; high compression alone cannot guarantee readiness.

Configured thresholds map to NO, EARLY, MODERATE, HIGH, and EXTREME compression. RELEASING requires boundary/turning evidence; EXPANDING requires exit, material spread expansion, follow-through, and the readiness threshold.

Directional lean requires multiple aligned location, volume, positioning, or completed release sources. Conflict returns UNCONFIRMED and absent context returns UNKNOWN.

## Quality, confidence, and degradation

Supported flags include candle missing/insufficient, invalid OHLC, ATR unavailable/zero baseline, range unavailable/zero width, volume/volatility/time/OI unavailable, proxy OI, missing typed dependencies, stale data, component conflict, and unconfirmed compression. Confidence incorporates valid rows, available components, agreement, dependencies, freshness, and malformed-row removal. Missing optional inputs and proxy OI apply explicit configured ceilings.

Missing/unusable critical OHLC returns UNAVAILABLE. Valid price data with missing optional volume/OI remains a partial capped-confidence result. Inputs are copied, sorted, deduplicated, cutoff-filtered where timestamps exist, and never mutated. No future data, providers, repositories, Streamlit calls, recommendation changes, or guaranteed-move language are used.
