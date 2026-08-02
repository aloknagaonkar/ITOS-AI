# Historical Replay Rules

Sprint 18.4A defines typed `LIVE`, `HISTORICAL_REPLAY`, and `SAMPLE_DATA` modes. A
provider creates the single `MarketSnapshot` consumed by the unchanged decision
pipeline; engines never acquire data. `ReplayRequest` validates instrument, India
trading date, supported interval, and the configured 09:15–15:30 Asia/Kolkata
session. After-close requests are rejected.

`ReplayMetadata` records analysis/cutoff/latest timestamps, sources, quality counts,
warm-up/session counts, protection flags, option status, and completeness. Candle
open timestamps are normalized to Asia/Kolkata, sorted, and duplicate timestamps
use stable keep-last. Naive timestamps mean Asia/Kolkata; aware/UTC values are
converted. A candle is included only when its open is strictly before the floored
interval boundary, so an in-progress candle is never exposed. Earlier-session
warm-up data is permitted; later data is counted and excluded.

Historical options are selected through an expiry/instrument-aware interface at or
before cutoff. Available data is `FULL_REPLAY`, partial contract state is
`PARTIAL_OPTION_REPLAY`, absence is `CANDLE_ONLY_REPLAY`; no fields are fabricated.
Samples are `SAMPLE_REPLAY`, fixed, and explicitly not for trading. Live is `LIVE`.
Unavailable acquisition is `UNAVAILABLE` at the application boundary.

Confidence, phase, stability, decision, strike, and trade histories are copied and
filtered at cutoff. Missing timestamps yield insufficient (empty) replay history,
not present-day history. Cache keys separate source, instrument, interval, date and
schema under `data/historical/candles`; JSON is the documented lightweight fallback
because parquet support is optional. Reads return new frames and corruption is a
safe miss. Secrets are never stored.

Identical inputs and source rows produce fresh, deterministic snapshots. Historical
failure is surfaced and must never fall back to live Upstox data. Sprint 18.4B owns
mode controls, timeline navigation, playback, and outcome UI; none is added here.
