# Upstox Institutional Market Intelligence & CE/PE Decision Engine v5

Version 5 retains the complete Version 4 institutional-flow dashboard and adds a volume-aware CE/PE decision layer.

## New in Version 5

- Market regime detection: trending, developing, range-bound, expansion, or low participation
- Underlying relative-volume confirmation
- Nearby CE/PE strike ranking using liquidity, volume, OI, OI change, delta, gamma, bid/ask spread, premium momentum and theta risk
- Decision states: `NO TRADE`, `WATCH CE/PE`, and `BUY SETUP CONFIRMED — CE/PE`
- Best-ranked contract with rule-based entry trigger, stop-loss and two planning targets
- Transparent blockers and confirmation evidence
- Existing SQLite snapshots, 5/15/30/60-minute OI flow, PCR/IV/Max Pain history, heatmaps, Greeks, VWAP, EMA and native Upstox chart are retained

## Run

1. Copy your existing `.env` file into this folder.
2. Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

3. Start Streamlit:

```powershell
py -m streamlit run app.py
```

For institutional history, enable auto-refresh at 60 seconds and keep SQLite snapshot storage enabled.

## Important

The setup score is a rule-based model score, not a statistically guaranteed win probability. Entry, stop and target values are planning levels. The application does not place orders.

## Version 5.2 — Historical Trade Tracker

- Automatically records every Top-5 candidate that changes to `TRIGGERED`.
- Keeps active trades yellow.
- Marks a completed trade green (`SUCCESS`) when Target 1 is reached.
- Marks a completed trade red (`FAILURE`) when the stop-loss is reached.
- Stores entry, latest/exit price, targets, stop, best/worst observed LTP, signal score, confidence and P&L.
- Shows total trades, active trades, success rate and average completed P&L.
- Provides a CSV download of the trade history.

Trade outcomes are evaluated from the latest option LTP available on each dashboard refresh. This is a decision-support and paper-tracking feature, not broker order execution.

## Version 6 additions

Version 6 preserves every Version 5.2 module and adds:

- Explainable component scores for Trend, OI/Institutional Flow, Volume, Premium Flow, Greeks, Liquidity and Risk/Reward
- Trade Quality and Health Score (0-100)
- Six-condition trigger checklist and visual countdown
- WAITING / READY-WATCH / TRIGGERED lifecycle display
- Live active-trade progress toward Target 1
- Historical journal fields for market regime, trade quality and health score
- Average winner, average loser and profit factor performance statistics
- Safe SQLite schema migration for existing `market_intelligence.db` files

Existing `.env` and `market_intelligence.db` files can be copied into the Version 6 folder. The database migration runs automatically.

## Version 6.1 — Calibrated Confidence Engine

Confidence is now calculated separately from trade quality. The engine combines independent evidence from trend, OI/institutional flow, volume, premium movement, Greeks, liquidity, risk/reward and the base model. It then applies conservative caps for low participation, compressed regimes, poor contract quality, insufficient chain data and active no-trade blockers.

The dashboard displays:

- Calibrated confidence and confidence band
- Expected confidence range
- Active confidence cap
- Weighted contribution table
- Confidence boosters and deductions
- Separate confidence for every Top 5 CE and PE candidate

High confidence does not guarantee a profitable outcome; it indicates stronger agreement among the measured inputs.

## Version 6.2 — Configurable Confidence & Consensus

- Standalone `confidence_engine.py` service shared by the recommendation layer.
- Editable `confidence_config.json` for signal weights, thresholds, penalties and confidence caps.
- Configuration validation: weights must total 1.0.
- Four-level confidence hierarchy: market, direction, trigger and calibrated confidence.
- AI consensus board showing agreement across Trend, OI, Volume, Premium, Greeks, Liquidity and Risk engines.
- SQLite `confidence_history` table records confidence evolution on each loaded refresh.
- Confidence trend chart shows whether conviction is building, stable or fading.
- Existing option analytics, Top 5 CE/PE board, triggered trade tracking and performance journal are preserved.

Restart Streamlit after changing `confidence_config.json` so the new settings are loaded cleanly. Validate changes against historical performance before using them in live decision-making.

## Version 7.0 — Institutional Cycle & Stability Foundation

Version 7.0 preserves all Version 6.2 features and introduces a plugin-ready engine framework.

### New modules

- `engines/base_engine.py` — common `analyze`, `score`, `explain`, `vote`, and persistence interface.
- `engines/registry.py` — engine registration and independent execution.
- `engines/market_cycle_engine.py` — classifies Compression, Accumulation, Manipulation, Bullish Expansion, Bearish Expansion, and Distribution.
- `engines/stability_engine.py` — measures recommendation consistency using direction changes, confidence variability, consensus agreement, phase consistency, and manipulation risk.

### New decision gates

A previously confirmed CE/PE setup is downgraded to WATCH when:

- the market is not in directional expansion;
- the Market Cycle direction conflicts with the recommendation;
- manipulation risk is active; or
- Recommendation Stability is below 70/100.

These engines can only block or downgrade an entry. They cannot create a BUY signal on their own.

### New SQLite history

The migration automatically creates:

- `phase_history`
- `stability_history`

Existing snapshot, confidence, and trade-history data remains unchanged.

### Dashboard additions

- Current market phase and phase confidence
- Probability table for all cycle phases
- Manipulation score and cycle vote
- Stability score, label, trend, and direction-change count
- Phase-transition history
- Stability trend chart
- Explainable reasons from both engines

### Important startup behaviour

The Stability Engine intentionally starts in **Developing** mode when little history is available. Keep one-minute snapshots enabled so stability can mature. This prevents a newly appearing high-confidence recommendation from becoming green immediately.


## Version 7.0 Layout Update

- Support, Resistance, Max Pain, and Spot/ATM are displayed at the top of the dashboard.
- Top 5 CE candidates are displayed first at full width.
- Top 5 PE candidates are displayed below CE candidates at full width.

## Version 7.1 — Institutional Intelligence

Version 7.1 converts the cycle and recommendation outputs into an explainable institutional brief.

### New engines

- `PhaseTransitionEngine` — identifies the likely next market phase and measures transition maturity.
- `PatternRecognitionEngine` — detects VWAP trend patterns, call/put writing, Wyckoff accumulation/distribution, compression breakout watch, directional expansion, and liquidity-sweep risk.
- `TradeReadinessEngine` — applies eight independent readiness controls across confidence, quality, cycle, stability, pattern alignment, consensus, and manipulation risk.
- `InstitutionalRadarEngine` — summarizes buying pressure, selling pressure, call writing, put writing, and institutional directional bias.
- `MarketStoryEngine` — produces a human-readable market narrative including current phase, likely transition, dominant pattern, readiness, recommendation, and remaining risk.

### Dashboard additions

- AI Institutional Brief at the top of the dashboard
- Current-to-next phase and transition probability
- Institutional buying/selling and writing radar
- Institutional checklist with PASS/WAIT status
- Primary, supporting, and conflicting patterns
- Explicit list of conditions still blocking readiness

The Version 7.1 engines explain and gate existing recommendations. They do not manufacture a BUY signal and do not replace risk management or trader judgment.

## Version 7.5 — Institutional Footprint Edition

Version 7.5 is additive: all Version 7.1 engines, dashboards, safety gates and recommendation logic remain intact.

New confirmation engines:

- Institutional Footprint Engine with Whale/Shark classification
- Smart Candlestick Engine (curated patterns only)
- Candle DNA and candle-strength scoring
- Institutional Structure Engine: Flat Base/Rectangle, W, M, Bull Flag, Bear Flag, Wyckoff Spring/Upthrust, volatility squeeze
- False-Breakout Engine
- Institutional Confirmation Engine and evidence matrix

A developing structure produces WATCH. A confirmed pattern cannot create a BUY signal on its own; it can only validate an existing CE/PE setup. High false-breakout risk or weak institutional confirmation can downgrade an existing trigger to WATCH/WAIT.

## Historical Smart Candle & Candle DNA (v7.5.2)

The dashboard now retrieves Upstox V3 historical minute candles and scans every
candle from the latest two trading sessions using the same Smart Candlestick and
Candle DNA engines used for the live signal.

The table includes date/time, detected pattern, CE/PE/WAIT direction, pattern
reliability, DNA score and grade, body/wick proportions, range-to-ATR, relative
volume, VWAP alignment and evidence. Filters and CSV download are included.


## Version 7.5.2 — Historical Pattern Intelligence

- Forward outcome tracking after 1, 3 and 5 candles
- MFE, MAE and R-multiple evaluation
- CONFIRMED, FAILED, INVALIDATED, UNRESOLVED and PENDING lifecycle states
- Historical confirmation score using Candle DNA, VWAP, EMA trend and relative volume
- Pattern performance statistics and evaluated win rate
- Interactive candlestick replay with entry, target and stop levels
- Explainable failure analysis and downloadable CSV evidence

Historical results are analytical observations, not guaranteed trade outcomes.

## Version 7.7 — Institutional Trade Planner

Adds an explainable Institutional Decision Matrix, AI strike selector, entry zone,
ATR/delta-aware stop, three risk-multiple targets, capital-risk position sizing,
trigger requirements, and dynamic exit guidance. Version 7.7 is planning-only:
it does not place broker orders and it preserves every Version 7.5.2 safety gate.


## Version 7.7 — Institutional Flow Engine

Adds minute-by-minute OI flow velocity and acceleration, call/put writing strength, delta/gamma flow, gamma-wall detection, IV expansion, liquidity/OI heatmap, institutional timeline, Institutional Confidence Engine (ICE), AI Early Warning, and a six-control Signal Validation Framework. Early warnings never place orders and BUY remains gated by the previous market-cycle, stability, false-breakout and institutional-confirmation controls.

For meaningful flow analysis, keep **Store snapshots in SQLite** enabled and collect at least four minute snapshots during market hours. Fifteen or more snapshots provide a more useful timeline.


## Version 8.0 — Core Institutional Intelligence

This milestone adds four explainable engines without removing any Version 7.7 safety gate:

- Market Regime Engine
- Smart Money Index
- Market Energy Engine
- Opportunity Lifecycle Engine

The lifecycle may show SCANNING, ACCUMULATION, VALIDATION or READY. READY is a decision-support state only and does not place an order.

## Version 8.1 — Historical Intelligence

Version 8.1 adds a historical evidence layer while preserving all live safety gates.

New capabilities:

- Historical Similarity Engine using stored session-level PCR, IV, OI, volume, confidence and market-state features.
- Decision Audit Engine with one reproducible evidence record per refresh minute.
- Institutional Playbook Engine with ranked live-session behaviours.
- Market Replay Engine for material price, confidence and state transitions.
- Explainable AI Session Report in plain English.
- CSV exports for similarity matches and decision-audit records.

Historical analysis requires stored snapshots across multiple trading sessions. It is supporting evidence only and cannot override live validation, false-breakout protection, stability or risk controls.
