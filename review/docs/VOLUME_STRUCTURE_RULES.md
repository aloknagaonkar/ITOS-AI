# Volume Structure Rules

## Facts
Price direction uses the normalized first-to-last slope over six closes with a 0.05% per-observation flat band. Price strength is clamped 0–100 from slope magnitude (35%), net percentage displacement (35%), and directional consistency (30%). Volume direction uses five observations, their slope/change, and recent mean relative to up to 20 preceding observations; an 8% band is flat. Volume strength is the larger deviation of trend or relative volume, scaled to 100. Absolute volume is never interpreted without its baseline.

## Confirmation and effort/result
Rising volume confirms rising or falling price; falling volume diverges; flat volume is neutral; unavailable volume is unavailable. Effort is relative volume and expansion. Result is multi-close displacement: at least 1.2x effort with at least 0.60% result is strong demand/supply; at least 1.2x effort with no more than 0.35% result is absorption; falling effort with a small continuing move is exhaustion; otherwise balanced/weak.

## Location matrix
Bottom/lower rising+rising is possible accumulation; rising+falling weak rally; falling+rising selling-climax risk; falling+falling weak decline. Top/upper falling+rising is possible distribution; rising+falling weak rally; rising+rising buying-climax risk; falling+falling weak decline. Middle rising+rising/falling+rising are bullish/bearish expansion; declining volume produces weak rally/decline. Rising breakout participation is expansion while declining-volume breakout is weak. An upward retest is a healthy pullback. Failed transitions become neutral and lose confidence.

## Scores
Accumulation combines 40 location points, 40 aligned rising-participation points, and up to 20 absorption points. Distribution mirrors this at upper locations with falling price/rising volume. Absorption combines elevated relative effort and limited result. Exhaustion combines below-baseline volume and its effort state. Every score is clamped 0–100 and expresses developing evidence, never certainty.

## Quality and missing data
Flags include `CANDLES_MISSING`, `CANDLES_INSUFFICIENT`, `OHLC_INVALID`, `VOLUME_MISSING`, `VOLUME_INVALID`, `VOLUME_BASELINE_UNAVAILABLE`, `MARKET_LOCATION_UNAVAILABLE`, `STALE_DATA`, and `CONFLICTING_STRUCTURE`. Missing/malformed candles, invalid/zero volume, or absent/unknown location returns unknown/unavailable facts, neutral interpretation, and 5% confidence.

## Configuration
Defaults are: minimum candles 8; price lookback 6; flat threshold 0.0005; price weights 35/35/30; volume lookback 5; baseline 20; volume flat band 0.08; confirmation threshold 0.05; high effort 1.20; large result 0.60%; absorption 1.25x/0.35%; exhaustion lookback 5; accumulation and distribution weights 40/40/20; stale threshold 1800 seconds. Values live in `VolumeStructureSettings` and may be supplied under `volume_structure` in existing context configuration.

Sprint 12 outputs are informational only and are not inputs to recommendations, confidence, safety, planning, or execution.

## Sprint 12 hardening clarification
OHLC validation also requires positive prices and a valid candle envelope (`low <= open/close <= high`). The configurable confirmation threshold is applied to volume-strength evidence before a moving-price observation can be called confirmed or diverging. The configured exhaustion window contributes shrinking-spread evidence; it does not create a recommendation. A moving price without enough confirmation evidence receives `EFFORT_RESULT_UNCONFIRMED`.
