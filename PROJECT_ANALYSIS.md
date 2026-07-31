# ITOS-AI Project Architecture Assessment

## Scope and assessment approach

This document describes the repository as it exists today. It is an architecture assessment and migration proposal, not a request to replace the working Streamlit application. The central constraint for ITOS 2.0 should be **strangler-style evolution**: retain the current calculations, safety gates, database, and dashboard while introducing stable boundaries around them.

## 1. Repository Structure

### Application entry point

- **`app.py`** is the 1,720-line Streamlit composition root, controller, session-state store, engine pipeline, persistence coordinator, and primary view. It handles OAuth/token input, market selection, Upstox calls, snapshot loading/saving, construction of every generation of intelligence engine, safety-gate mutation, trade tracking, and almost all dashboard panels.

### Broker and data acquisition

- **`upstox_client.py`** is the active synchronous REST adapter. `UpstoxClient` exchanges OAuth codes, lists option expiries, loads option chains, loads V3 intraday/historical candles, validates HTTP responses, and converts Upstox payloads into pandas DataFrames.
- **`data_stream/`** is an unfinished live-streaming scaffold. `LiveCache` only declares quote/depth/Greeks dictionaries; `StreamManager` is empty; `UpstoxWebSocketClient` exposes placeholder methods. None participates in the dashboard data path.
- **`itos_platform/`** contains forward-looking, broker-neutral contracts: `DataProvider`, `MarketDataEnvelope`, and `ProviderHealth`. The active `UpstoxClient` does not implement these contracts, and the application does not consume envelopes.

### Legacy analytics and recommendation services

- **`ai_engine.py`** converts an option-chain DataFrame into max-pain, buildup, strike-level analytics, and an aggregate option-market summary.
- **`market_intelligence.py`** enriches OHLCV candles with EMA, VWAP, ATR, RSI, and volume features; scores price action; then combines price and option evidence into the live directional intelligence dictionary.
- **`institutional_engine.py`** derives multi-window and strike-level institutional flow from persisted snapshot history and produces a narrative summary.
- **`confidence_engine.py`** is the configurable confidence calculator used by the legacy recommendation path. It reads `confidence_config.json`, validates weights, calculates consensus, applies caps/penalties, labels confidence, and calibrates candidate confidence.
- **`recommendation_engine.py`** is the active base decision service. It detects a market regime, independently ranks CE and PE contracts, computes component and side strengths, applies blockers and a trigger checklist, decorates candidates with execution levels, and returns the large mutable recommendation dictionary consumed downstream.

### Pluggable engine package

- **`engines/base_engine.py`** defines the common `BaseEngine.analyze()` interface and normalized `EngineResult` envelope.
- **`engines/registry.py`** can register and run engines, but is not used by `app.py`.
- **`engines/market_cycle_engine.py`** and **`engines/stability_engine.py`** implement the first safety-gating layer.
- **`engines/institutional_intelligence.py`** contains phase transition, pattern recognition, readiness, radar, and market-story interpretation.
- **`engines/institutional_confirmation.py`** contains candle DNA, smart-candle, historical pattern analysis, structure, footprint, false-breakout, and confirmation logic.
- **`engines/trade_planner.py`** contains the decision matrix and position-sized execution planner.
- **`engines/institutional_flow.py`** contains snapshot-derived flow, a second institutional confidence implementation, signal validation, and early warning.
- **`engines/core_intelligence.py`** contains regime, smart-money, energy, and opportunity-lifecycle summaries.
- **`engines/historical_intelligence.py`** contains similarity, playbook, replay, and session-report engines.
- **`engines/decision_intelligence.py`** aggregates votes into probability, risk, reasoning, invalidation, and a final decision package.
- **`engines/data_health_engine.py`** measures completeness and freshness of the active data payload.
- **`engines/ai_trade_engine.py`** adapts the mutable recommendation and planner outputs into the typed dashboard-facing trade opportunity.
- **`engines/explainable_ai.py`** deduplicates and prioritizes supporting reasons and blockers for that opportunity.
- **`engines/ai_orchestrator.py`**, **`engines/institutional_confidence.py`**, and **`engines/strike_ranker.py`** form a separate, newer orchestration path exercised by the smoke tests but not by `app.py`.
- **`engines/__init__.py`** re-exports most active engine types. Import ordering currently makes `InstitutionalConfidenceEngine` mean the implementation from `institutional_flow.py`, not the same-named class in `institutional_confidence.py`.

### Persistence

- **`snapshot_store.py`** owns the SQLite schema, migration, and repositories for market/strike snapshots, confidence, phase, stability, tracked trades, decision audits, and playbook history. `SnapshotStore` also contains trade lifecycle and statistics business logic.
- **`market_intelligence.db`** is a committed runtime SQLite database. It is data/state rather than source code and currently couples a repository checkout to one captured environment.

### Domain models and presentation

- **`models/trade.py`** defines immutable `TradeCandidate`, `ExecutionPlan`, and `AITradeOpportunity` dataclasses. This is the clearest existing typed boundary between decision logic and UI.
- **`ui/ai_trade_card.py`** renders the decision-first hero card, trigger checklist, early warning, evidence, execution plan, and CE/PE candidate tables.
- **`charting.py`** renders the current market chart; **`history_charts.py`** renders historical trend, OI-flow, and strike heatmap figures.
- Most remaining presentation code is still embedded directly in `app.py`.

### Tests, configuration, documentation, and assets

- **`tests_test_v921.py`** is a three-case executable/pytest smoke suite for the separate `AIOrchestrator` path.
- **`requirements.txt`** lists the runtime stack but has no development/test tooling and uses lower bounds only.
- **`confidence_config.json`** externalizes legacy confidence weights, thresholds, penalties, and caps.
- **`README.md`**, **`CHANGELOG.md`**, **`VERSION.md`**, `VALIDATION.md`, and numerous **`RELEASE_NOTES_*.md`** files record the additive version history. Their version labels are not consistently aligned with the dashboard title/captions.
- **`assets/custom_candles/`** contains the injection-pinbar-bottom specification and reference image; the specification is not wired into a general plugin loader.

## 2. Current Architecture

### Live data flow: Upstox to dashboard

1. Streamlit executes `app.py` top to bottom. The sidebar obtains an access token from environment/session input, accepts underlying/timeframe/strike/history settings, and calls `UpstoxClient.get_option_expiries()`.
2. On a button click or auto-refresh, `UpstoxClient` synchronously retrieves the selected option chain, current intraday candles, and (best effort) dated historical candles. REST errors are translated to `UpstoxAPIError`.
3. `option_chain_to_dataframe()` normalizes nested Upstox call/put market data and Greeks into one row per strike. `analyse_market()` narrows strikes around ATM and produces `option_result = {chain, summary}`.
4. `evaluate_price_action()` turns intraday candles into technical features and a price score. `combine_intelligence()` combines option and price scores into `intelligence`, including state, confidence, evidence, risks, and the enriched candle frame.
5. `option_result`, `intelligence`, selection metadata, and historical candles are placed in `st.session_state`. When enabled, `SnapshotStore.save_snapshot()` stores one market and strike snapshot per minute.
6. Historical market and strike snapshots are reloaded and passed to `institutional_summary()`. `build_recommendation()` combines the current option/price payload with this optional history and returns the initial CE/PE recommendation, rankings, confidence, blockers, and plan levels.
7. `app.py` manually invokes engines in dependency order:
   - cycle and stability;
   - phase/pattern/readiness/radar/story;
   - candle/structure/footprint/false-breakout/confirmation;
   - decision matrix;
   - institutional flow/confidence/validation/early warning;
   - regime/smart-money/energy;
   - later, inside the live tab, trade planning, lifecycle, historical intelligence, and decision intelligence.
8. Results are primarily passed as ad hoc dictionaries containing earlier `EngineResult` objects. Their `metadata` dictionaries are copied back into the central recommendation dictionary.
9. `app.py` imperatively applies hard vetoes after initial recommendation creation. Cycle, stability, false-breakout, institutional confirmation, and flow validation can downgrade a confirmed trade. It then mutates Top-5 candidate states to remain consistent with the final gate.
10. Persistence is updated for phase, stability, confidence, tracked trades, decision audit, and playbook history. Historical records are also read back for charts, replay, and similarity analysis.
11. `AITradeEngine` converts the recommendation into typed `AITradeOpportunity`/`ExecutionPlan`/`TradeCandidate` objects. `render_ai_trade_opportunity()` displays the decision-first card; the remainder of `app.py` renders detailed live and explorer panels directly with Streamlit and Plotly.

### Important runtime characteristics

- The system is a **single-process, synchronous Streamlit application**. Refresh is polling/rerun based, not websocket based.
- The authoritative decision is not one engine: it is the base recommendation plus ordered mutations and vetoes in `app.py`.
- SQLite is both history storage and an input to subsequent analysis. A cold database deliberately yields developing/wait states for several engines.
- Historical candles from Upstox and historical snapshots from SQLite are separate evidence sources.
- The `AIOrchestrator`/`StrikeRanker` route operates on a flatter market-data schema and currently runs only in the smoke test, not the dashboard.

## 3. Existing Engines

Unless noted otherwise, class engines depend on Python, NumPy/pandas where imported, and the local `BaseEngine`/`EngineResult` contract. Their standard output is an `EngineResult` containing a 0–100 score, normalized vote, explanation list, confidence/weight, and engine-specific metadata.

### Foundational/legacy engines

| Engine or service | Purpose | Input | Output | Direct dependencies |
|---|---|---|---|---|
| `ai_engine.analyse_market` | Summarize option positioning, PCR, IV skew, max pain, support/resistance, and buildup near ATM. | Normalized option-chain DataFrame; strike radius. | Dictionary with analyzed chain and option summary/score/reasons. | pandas, NumPy. |
| `market_intelligence.evaluate_price_action` | Calculate technical candle features and directional price evidence. | OHLCV DataFrame. | Price dictionary containing enriched candles, indicators, score, and reasons. | pandas, NumPy. |
| `market_intelligence.combine_intelligence` | Blend option and price evidence and identify conflict/no-trade conditions. | Option result and price result dictionaries. | Intelligence dictionary with state, score, confidence, probabilities, evidence, flags, and price data. | NumPy; upstream payload conventions. |
| `institutional_engine.institutional_summary` | Measure 5/15/30/60-minute and strike-level OI/premium flow and narrate institutional behavior. | Snapshot and strike-history DataFrames. | Institutional summary dictionary and flow tables. | pandas, NumPy, `WindowChange`. |
| `recommendation_engine.build_recommendation` | Produce the active base CE/PE recommendation and ranked candidates. | Option result, intelligence, optional institutional summary. | Large dictionary: side/status/confirmed, confidence, rankings, checklist, blockers, component scores, regime, and planning levels. | pandas, NumPy, `confidence_engine`, helpers in same module. |
| `confidence_engine.build_confidence` | Calibrate confidence independently from trade quality and apply consensus/caps. | Intelligence, component scores, regime, selected row, blockers, chain size, direction, configuration. | Confidence detail dictionary; `candidate_confidence` provides per-contract calibration. | JSON configuration, pathlib, NumPy. |

### Cycle, interpretation, and confirmation engines

| Engine | Purpose | Input keys | Principal output metadata | Notable dependencies |
|---|---|---|---|---|
| `MarketCycleEngine` | Classify compression, accumulation, manipulation, expansion, or distribution and gate trading. | `option_result`, `intelligence`, `institutional`. | Phase, phase probabilities/confidence, manipulation score, direction, `trade_allowed`. | Candle DataFrame plus option/history summaries. |
| `RecommendationStabilityEngine` | Measure consistency across recent recommendations and phases. | `recommendation`, confidence/phase history DataFrames, `cycle_result`. | Stability score/label/trend, direction-change count, pass flag. | pandas/NumPy and persisted history. |
| `PhaseTransitionEngine` | Predict likely next cycle phase and transition maturity. | `cycle_result`. | Current/next phase, transition probability, maturity. | Cycle metadata. |
| `PatternRecognitionEngine` | Identify price/OI institutional patterns and conflicts. | Recommendation, option result, intelligence, institutional summary, cycle result. | Primary/supporting/conflicting patterns and vote. | Existing result dictionaries/objects. |
| `TradeReadinessEngine` | Apply eight readiness controls without creating a trade. | Recommendation, cycle, stability, pattern. | Checklist, passed/missing counts, readiness status. | Upstream metadata. |
| `InstitutionalRadarEngine` | Summarize buying, selling, call writing, put writing, and directional bias. | Recommendation, option result, institutional summary, intelligence. | Pressure values and institutional bias. | Option/current/history summaries. |
| `MarketStoryEngine` | Turn the interpretation layer into a human-readable brief. | Recommendation and cycle/transition/readiness/radar/pattern results. | Story text and risk level. | Upstream `EngineResult` metadata. |
| `CandleDNAEngine` | Score current candle body/wicks/range, volume, and VWAP/EMA context. | `intelligence.price.candles`. | DNA components, grade, evidence, direction. | pandas/NumPy candle features. |
| `SmartCandlestickEngine` | Detect a curated set of high-value recent candle patterns. | Intelligence or candle-oriented market payload. | Primary pattern and all detected patterns. | Candle DNA-style context and pandas/NumPy. |
| Historical candle functions | Scan two sessions and evaluate forward outcomes/statistics. | Candle DataFrame, trading-day and evaluation-bar settings. | Pattern-event and aggregate-statistics DataFrames. | Smart candle/DNA rules, pandas/NumPy. |
| `InstitutionalStructureEngine` | Detect bases, W/M structures, flags, springs/upthrusts, and squeezes. | `intelligence.price.candles`. | Primary structure and structure list. | pandas/NumPy. |
| `InstitutionalFootprintEngine` | Classify large-player activity and directional footprint. | Option summary, price, institutional summary, cycle. | Activity/classification/direction and component evidence. | Existing summaries. |
| `FalseBreakoutEngine` | Estimate trap risk and veto unsafe breakouts. | Structure, candle DNA, footprint, cycle results. | Risk score/label/reasons and `blocked`. | Upstream metadata only. |
| `InstitutionalConfirmationEngine` | Weighted confirmation matrix across footprint, structure, candles, pattern, and cycle. | Recommendation plus six confirmation results and false-breakout result. | Rows, confirmation score/status, conflict weight, trap risk. | Upstream results. |

### Planning, flow, and core intelligence engines

| Engine | Purpose | Input keys | Principal output metadata | Notable dependencies |
|---|---|---|---|---|
| `InstitutionalDecisionMatrixEngine` | Aggregate cross-engine evidence before planning. | Recommendation, intelligence, cycle, footprint, confirmation, candle DNA, pattern, false breakout. | Matrix rows, overall score, status, direction. | Upstream results. |
| `AITradePlannerEngine` | Select the active ranked contract and calculate entry zone, ATR/delta-aware stop, targets, risk/reward, lots, and quantity. | Recommendation, intelligence, decision matrix, capital, risk percent, lot size. | Structured plan and sizing data; WAIT if no valid contract. | pandas, NumPy, math. |
| `InstitutionalFlowEngine` | Calculate minute-level OI velocity/acceleration, writing strength, Greeks/IV flow, walls, heatmap, and timeline. | Market and strike history DataFrames, recommendation, option result. | Flow direction/strength, components, timeline/heatmap, snapshot sufficiency. | pandas, NumPy and stored snapshots. |
| `institutional_flow.InstitutionalConfidenceEngine` | Combine the current recommendation with flow, confirmation, cycle, candle, pattern, and decision-matrix evidence. | The named upstream results. | ICE score, aligned evidence rows, grade/status. | Upstream `EngineResult` objects. |
| `SignalValidationEngine` | Require six safety controls before allowing the existing trigger. | Recommendation, flow, ICE, confirmation, false breakout, stability. | Checks, passed/total, `validated`. | Upstream results. |
| `EarlyWarningEngine` | Detect developing setup direction/probability without authorizing entry. | Recommendation, flow, ICE, validation. | Early side/state/probability and informational-only status. | Upstream results. |
| `MarketRegimeEngine` | Summarize live session type from volatility, trend, flow, and cycle evidence. | Option result, intelligence, flow, cycle. | Regime, direction, confidence, metrics. | NumPy and upstream metadata. |
| `SmartMoneyIndexEngine` | Weighted composite of institutional/confirmation/risk evidence. | Recommendation, flow, ICE, confirmation, regime, stability, false breakout. | SMI score/bias/components. | Upstream results. |
| `MarketEnergyEngine` | Measure whether directional participation has enough energy. | Recommendation, option result, intelligence, flow. | Energy score/state/direction/components. | NumPy and current/flow evidence. |
| `OpportunityLifecycleEngine` | Classify SCANNING, ACCUMULATION, VALIDATION, or READY. | Recommendation, ICE, validation, early warning, SMI, energy, trade plan. | Stage, probability, requirements. | Upstream results. |

### Historical and final decision engines

| Engine | Purpose | Input keys | Principal output metadata | Notable dependencies |
|---|---|---|---|---|
| `HistoricalSimilarityEngine` | Compare current session features with completed stored sessions. | Long snapshot-history DataFrame and current feature dictionary. | Similar matches, readiness/status, similarity score/vote. | pandas/NumPy and adequate multi-session history. |
| `InstitutionalPlaybookEngine` | Rank recognizable session playbooks. | Regime, flow, energy, pattern, intelligence, option result. | Ranked playbooks and primary playbook. | Upstream results. |
| `MarketReplayEngine` | Extract material price/confidence/state transitions from history. | Snapshot-history DataFrame. | Replay event list and status. | pandas/NumPy. |
| `ExplainableSessionReportEngine` | Generate a concise natural-language session report. | Regime, SMI, energy, similarity, playbook, recommendation. | Report and grade. | Upstream results. |
| `AIConsensusEngine` | Build a weighted committee vote and quantify conflicts. | Recommendation, decision matrix, validation, regime, flow, SMI, energy, candle DNA, pattern, similarity, playbook. | Vote rows, consensus/conflict, final vote. | Upstream results. |
| `TradeProbabilityEngine` | Convert consensus plus historical and validation evidence into CE/PE/WAIT probabilities. | Consensus, similarity, validation. | Probability distribution and leading confidence. | NumPy and upstream results. |
| `EnhancedRiskValidationEngine` | Apply critical risk controls with veto authority. | Recommendation, consensus, probability, validation, stability, false breakout, confirmation, trade plan. | Risk score/level, blockers, veto flag. | Upstream results and planner metadata. |
| `DecisionReasoningEngine` | Produce a trace explaining the committee decision and risk result. | Consensus, risk, recommendation. | Reasoning trace and decision context. | Upstream results. |
| `InvalidationEngine` | Define side-specific invalidation rules. | Consensus result. | Rule list and side. | Consensus vote. |
| `DecisionPackageEngine` | Assemble the final dashboard decision package. | Consensus, probability, risk, reasoning, invalidation, recommendation, plan, regime, lifecycle, playbook. | Final recommendation/status/confidence, plan, reasoning, invalidations, regime/playbook context. | `DecisionPackage` dataclass and all final-stage results. |
| `DataHealthEngine` | Score whether option, candle, recommendation, and refresh data is present/fresh enough. | Option result, intelligence, recommendation, last-refresh text. | Health grade, issue list, component checks. | Datetime and payload conventions. |
| `AITradeEngine` | Adapt legacy/current outputs to a stable UI model. | Recommendation and optional plan, matrix, regime, flow, confidence history. | `AITradeOpportunity` with candidates, execution plan, evidence, blockers, and recent changes. | pandas, trade dataclasses, `ExplainableAIEngine`. |

### Parallel v9.2 scaffold engines

| Engine | Purpose | Input | Output | Dependencies/status |
|---|---|---|---|---|
| `institutional_confidence.InstitutionalConfidenceEngine` | Calculate directional institutional confidence from a flat, broker-neutral-ish payload with completeness-aware weights. | Flat fields such as CE/PE OI change, PCR, volumes, spot/VWAP, Greeks, max pain, trend, futures. | `EngineResult` with components, completeness, grade, directional vote/confidence. | `BaseEngine`; only used by `AIOrchestrator` tests. |
| `StrikeRanker` | Rank list-of-dict option contracts by spread, activity, delta, moneyness, IV, and side fit. | Strike dictionaries, side, optional spot/limit. | Ranked list of `RankedStrike` dictionaries. | Standard library; only used by alternate orchestrator/tests. |
| `AIOrchestrator` | Isolate engine failures, aggregate weighted votes, calculate conflict/confidence, and attach ranked strikes. | Flat market dictionary plus configured engines/weights. | Explainable dashboard dictionary with decision, grade, vote shares, best strikes, engine results/errors. | Alternate confidence engine and `StrikeRanker`; not connected to Streamlit. |
| `EngineRegistry` | Register uniquely named `BaseEngine` instances and run them independently. | Engine instances and one shared market-data dictionary. | Mapping of engine names to results. | `BaseEngine`; currently unused. |

## 4. Problems Found

### Duplicate logic and competing models

- Numeric coercion/clipping helpers (`_safe`, `_num`, `_clip`, `_clamp`) are repeated throughout the root services and engine modules.
- Vote normalization and CE/PE/BULLISH/BEARISH mapping are independently reimplemented in several files.
- There are **two classes named `InstitutionalConfidenceEngine`** with different input contracts and scoring semantics, plus the legacy configurable `confidence_engine.py`. The public `engines` import resolves to one implementation while `AIOrchestrator` imports the other directly.
- Strike ranking exists twice: DataFrame-based `recommendation_engine.rank_strikes()` drives the dashboard, while list-based `engines.strike_ranker.StrikeRanker` drives only the alternate orchestrator tests.
- Regime concepts are calculated in `recommendation_engine.detect_market_regime`, `MarketCycleEngine`, and `core_intelligence.MarketRegimeEngine`. They serve different generations but have overlapping names and thresholds.
- Recommendation aggregation is split among `build_recommendation`, manual gates in `app.py`, `InstitutionalDecisionMatrixEngine`, `AIConsensusEngine`, `DecisionPackageEngine`, and the disconnected `AIOrchestrator`.
- Trade-plan values can originate in the recommendation decorator, `AITradePlannerEngine`, and fallback logic in `AITradeEngine`.

### Dead, dormant, or incomplete code

- `data_stream` websocket/cache/manager code is placeholder-only and unused.
- `itos_platform.DataProvider` and its envelopes are well-intentioned but not implemented by `UpstoxClient` or consumed by the app.
- `EngineRegistry` is unused; `app.py` instantiates every engine manually.
- The alternate `AIOrchestrator`, confidence engine, and strike ranker are tested but do not affect the dashboard. They are not necessarily deletable—their design is a useful migration seed—but they are dormant in production.
- `BaseEngine.save_history()` is an unused no-op while persistence is orchestrated explicitly in `app.py` and `SnapshotStore`.
- Compatibility helpers such as module-level `institutional_confidence.score()` and `strike_ranker.rank()` have no in-repository callers.
- The custom candle asset is documentation/reference data rather than a registered plugin.

### Tight coupling

- `app.py` depends on concrete `UpstoxClient` and `SnapshotStore` constructors throughout, so data source and persistence cannot be substituted in tests or at runtime.
- Engines accept untyped `dict[str, Any]`, know nested keys produced by many other engines, and frequently use `getattr(result, "metadata", {})`. Renaming a metadata key can silently change a downstream score.
- The order of calls in `app.py` is an implicit dependency graph. There is no declared engine dependency, schema validation, or topological executor.
- Business rules and safety gates live both inside engines and in the UI controller. Final behavior therefore depends on imperative mutation order.
- `SnapshotStore` combines schema migration, repositories, trade state transitions, analytics/statistics, and retention.
- Several engines depend directly on pandas DataFrames, preventing a clean domain/data boundary and making serialization/caching contracts implicit.

### Large classes/modules and mixed responsibilities

- `app.py` is the dominant problem: acquisition, orchestration, state, persistence, error handling, business policy, and presentation coexist in one rerun script.
- `snapshot_store.py` is large and multi-purpose, with persistence and trade-domain behavior in one class.
- `recommendation_engine.py` combines regime classification, ranking, confidence, early detection, checklist policy, plan decoration, and final decision construction.
- `engines/institutional_confirmation.py` combines live candle engines, historical event generation/evaluation, structures, footprint, trap detection, and aggregation.
- Large dictionary outputs make these modules harder to split safely because no explicit contract identifies which fields are public.

### Missing abstractions

- No active broker-neutral market-data gateway; the existing contract is disconnected from the implementation.
- No canonical domain snapshot combining chain, candles, selection, timestamps, and data-quality information.
- No typed input/output contracts for recommendation and intermediate engine evidence. Only final trade UI models are typed.
- No orchestration service for dependency ordering, gate policy, and failure behavior.
- No repository interfaces/unit-of-work boundary around SQLite.
- No clock abstraction; timestamps and freshness depend on scattered `date.today()`, `time`, and `datetime.now()` calls.
- No centralized configuration/settings object for thresholds, engine weights, time windows, and feature switches.
- No structured logging/telemetry or explicit audit of engine execution failures in the active path.

### Technical debt and operational risk

- Automated coverage is only three smoke tests and targets the non-dashboard orchestration path. The active recommendation, gates, persistence migration, Upstox normalization, and Streamlit composition lack regression tests.
- The test filename is nonstandard (`tests_test_v921.py`) and there is no dedicated `tests/` package or fixtures.
- Broad `except Exception` blocks preserve dashboard availability but can conceal programming/data-contract errors; some historical fallbacks intentionally degrade without structured diagnostics.
- The committed runtime database risks repository growth, accidental data leakage, nondeterministic local behavior, and merge conflicts.
- Dependency lower bounds without a lock/constraints file reduce reproducibility.
- Version strings conflict across the title, sidebar, UI captions, `VERSION.md`, README, and release notes.
- README begins at Version 5 while the code advertises Version 9.x; architecture and operator instructions are distributed across additive release notes.
- Option-chain normalization contains a duplicated `call_bid` dictionary key, indicating copy/paste debt even though the latter value simply overwrites the former.
- The active hero opportunity is constructed before the UI creates `trade_plan_result`, so it necessarily uses fallback planning data during that render. Later planner/decision results do not rebuild the already-rendered card in the same pass.
- `engine_store = SnapshotStore()` is created even when snapshot saving is disabled, and many separate store objects/connections are created per rerun.
- Safety behavior is correct in intent but difficult to prove: engines are described as “cannot create a BUY,” yet enforcement is convention plus manual mutation rather than a centralized monotonic gate policy.

## 5. Reuse Plan

“Unchanged” below means preserve behavior and public shape during early migration; internal changes should wait until characterization tests exist.

### Keep unchanged initially

- Preserve **all dashboard layouts and render behavior**, especially `ui/ai_trade_card.py`, `charting.py`, `history_charts.py`, and existing panels in `app.py`.
- Preserve `UpstoxClient` request/conversion behavior behind a new adapter boundary.
- Preserve SQLite schema and `SnapshotStore` public methods so existing databases remain compatible.
- Preserve `analyse_market`, `evaluate_price_action`, `combine_intelligence`, `institutional_summary`, and `build_recommendation` as compatibility services.
- Preserve every existing safety threshold and downgrade rule until golden-master tests demonstrate equivalence.
- Preserve `BaseEngine`, `EngineResult`, and the final trade dataclasses; extend them compatibly rather than replace them.
- Preserve confidence configuration and all historical records/exports.

### Refactor behind compatibility facades

- Reduce `app.py` to Streamlit page composition by extracting an `ApplicationService`/`DashboardPipeline` that returns one view model. Initially, this service should call the exact existing functions in the exact current order.
- Make `UpstoxClient` implement a data-provider adapter or wrap it with `UpstoxDataProvider`; do not change its HTTP behavior in the same step.
- Split `SnapshotStore` internally into snapshot, trade, confidence/cycle, and audit/playbook repositories while retaining a delegating `SnapshotStore` facade.
- Split recommendation calculation into side ranking, confidence, readiness policy, and recommendation assembly, preserving the current dictionary via an adapter.
- Split historical candle evaluation from live confirmation engines.
- Introduce typed, versioned evidence models gradually at module boundaries and provide `.from_legacy_dict()`/`.to_legacy_dict()` adapters.
- Turn manual engine invocation into a declarative pipeline with explicit dependencies, but retain the current sequence and fail/degrade policy first.

### Merge/consolidate

- Consolidate numeric coercion, clipping, vote normalization, and result-access helpers into one small compatibility utility module.
- Establish one canonical strike-ranking domain service with adapters for DataFrame and list payloads. Keep legacy scores unchanged until parity tests pass.
- Give confidence implementations distinct names immediately (for example, `ConfigurableRecommendationConfidence`, `FlowConfidence`, and `FlatPayloadInstitutionalConfidence`), then converge shared calibration primitives without pretending their different models are equivalent.
- Consolidate final safety gates into one monotonic `DecisionPolicy`: upstream engines may propose or support a side, but only policy can promote/downgrade final action and vetoes can never be reversed downstream.
- Merge `EngineRegistry` and the useful failure-isolation/weighting concepts from `AIOrchestrator` into the future pipeline runner, rather than maintaining two orchestration mechanisms.

### Remove only after proving non-use

- Remove compatibility helper functions only after repository and downstream consumer searches plus a deprecation period.
- Remove the placeholder `data_stream` implementation if websocket delivery is explicitly out of ITOS 2.0 scope; otherwise replace it incrementally with a real provider and cache behind the same market-data port.
- Remove one duplicate confidence and one duplicate ranking implementation only after the active dashboard is migrated and score parity/accepted behavior changes are documented.
- Stop tracking `market_intelligence.db`; retain the file locally through `.gitignore` and provide an empty migration-created database or sanitized fixture for tests. Do not delete a user's runtime database during migration.
- Archive/summarize superseded release notes only after preserving their operational and migration content in durable documentation.

## 6. ITOS 2.0 Proposal

### Target architecture

Use a modular monolith with explicit ports and adapters. A service split or event platform is unnecessary for the current load and would increase operational risk.

```text
Streamlit pages/components
        |
        v
DashboardApplicationService  ---> DashboardViewModel / AITradeOpportunity
        |
        +--- MarketDataPort <--- Upstox REST adapter
        |                     <-- future Upstox websocket adapter + LiveCache
        |
        +--- DecisionPipeline
        |       +--- feature builders (option, price, historical)
        |       +--- analysis engines (declared dependencies)
        |       +--- consensus/probability
        |       +--- monotonic SafetyGatePolicy
        |       +--- planner and explainability
        |
        +--- Repository ports <--- SQLite repositories
        |
        +--- Clock / Settings / Telemetry
```

### Proposed layers

1. **Domain**
   - Immutable `MarketSnapshot`, `OptionChain`, `CandleSeries`, `Evidence`, `EngineDecision`, `Recommendation`, `SafetyGate`, and `ExecutionPlan` models.
   - Canonical enums for `Side`, `Vote`, `DecisionState`, lifecycle, regime, and data quality.
   - No Streamlit, requests, SQLite, or pandas requirement in the core policy types. pandas may remain inside analytics adapters where it provides value.

2. **Application**
   - `LoadMarketSnapshot`, `RunDecisionPipeline`, `PersistDecision`, and `BuildDashboardView` use cases.
   - A declared pipeline graph specifying engine ID, required inputs, optional inputs, failure policy, and output schema.
   - One `SafetyGatePolicy` that receives the proposed recommendation plus all veto evidence and returns the only authoritative final decision.

3. **Ports**
   - `MarketDataProvider`, repository interfaces, `Clock`, and optional event/cache interfaces.
   - Extend the existing `itos_platform` contracts rather than inventing an unrelated abstraction.

4. **Adapters**
   - Current Upstox REST client, SQLite implementation, pandas-based legacy analytics, and future websocket/cache implementation.
   - Legacy dictionary adapters allow old engines to coexist with typed engines.

5. **Presentation**
   - Streamlit pages/components consume a single immutable dashboard view model and issue application commands.
   - Preserve current labels, order, charts, colors, and session behavior throughout migration.

### Key architectural policies

- **One canonical data snapshot per rerun:** attach provider/source timestamps and quality flags so every engine evaluates the same captured market state.
- **Monotonic decision safety:** only the policy layer emits BUY; any veto downgrades BUY to WATCH/WAIT and no later supporting engine can restore it during the same evaluation.
- **Explicit warming-up behavior:** insufficient history is a typed state, not an arbitrary low score or swallowed exception.
- **Schema/version discipline:** engine inputs and persisted audit payloads carry versions. Adapters absorb legacy dictionary differences.
- **Deterministic evaluation:** inject time/settings, record configuration version, and persist enough inputs/results to replay a decision.
- **Graceful isolation:** noncritical explanatory engines may fail without breaking the dashboard; acquisition, canonical feature building, and safety policy failures must produce a safe WAIT with a visible health reason.
- **No premature distributed architecture:** keep one deployable application and SQLite initially; clean boundaries make later replacement possible if scale actually requires it.

## 7. Migration Plan

### Phase 0 — Baseline and safety net

1. Capture representative sanitized Upstox chain/candle payloads and SQLite histories.
2. Add characterization tests for option normalization, base scores, CE/PE ranking, every veto, cold-history behavior, trade tracking, and the final `AITradeOpportunity`.
3. Add a headless Streamlit smoke check and golden snapshots of decision-critical view-model fields.
4. Record the current engine thresholds and version/config hash in decision audits.
5. Make no behavior changes in this phase.

### Phase 1 — Extract orchestration without changing results

1. Move the acquisition-through-final-decision sequence from `app.py` into a `DashboardApplicationService` using the existing functions/classes unchanged.
2. Return an aggregate result containing all values currently referenced by both tabs.
3. Keep session-state keys and rendering code stable; `app.py` becomes a caller of the service.
4. Run old and extracted paths against fixtures and assert field-level parity before deleting the in-page orchestration.

### Phase 2 — Activate data and persistence ports

1. Wrap `UpstoxClient` in the existing provider contract, expanding the request/envelope types carefully.
2. Inject the provider, clock, and one `SnapshotStore` facade into the application service.
3. Split repositories internally while preserving schema, migrations, database path, and facade methods.
4. Stop tracking runtime DB state and introduce sanitized fixtures; never automatically remove an operator's local database.

### Phase 3 — Introduce typed contracts at the edges

1. Create canonical market snapshot and evidence types.
2. Add adapters from the current `option_result`, `intelligence`, institutional summary, and `EngineResult.metadata` dictionaries.
3. Migrate one leaf engine at a time, beginning with engines having few dependencies (data health, phase transition, false breakout).
4. Keep legacy and typed outputs in shadow comparison until equivalent on recorded sessions.

### Phase 4 — Centralize the engine graph and safety policy

1. Enhance/replace `EngineRegistry` with declared dependencies and deterministic ordering based on the current `app.py` sequence.
2. Incorporate `AIOrchestrator` failure isolation, but classify engines as critical, safety-critical, or optional so exceptions cannot accidentally weaken gates.
3. Move cycle/stability/confirmation/false-breakout/flow veto mutations into `SafetyGatePolicy` and prove parity with characterization tests.
4. Persist proposed decision, every gate outcome, and final decision for auditability.

### Phase 5 — Reconcile duplicates

1. Rename confidence implementations to expose their true roles and remove ambiguous package exports.
2. Put DataFrame/list adapters around a single strike-ranking interface; compare both algorithms and explicitly approve any score changes.
3. Centralize numeric/vote helpers and migrate modules mechanically.
4. Consolidate planner fallbacks so the hero card and detailed planner use one plan generated before rendering.
5. Deprecate the inactive orchestration path only after the dashboard uses its replacement and tests move to the active pipeline.

### Phase 6 — Modularize presentation

1. Extract existing Streamlit panels into view functions/components without changing displayed content.
2. Pass typed view models rather than the mutable recommendation dictionary.
3. Preserve tab order, widget keys/session state, refresh behavior, and chart semantics.
4. Use screenshot regression checks for perceptible UI changes.

### Phase 7 — Optional live streaming

1. Decide whether websocket streaming is an actual product requirement.
2. If yes, implement `UpstoxWebSocketClient`, `LiveCache`, and `StreamManager` behind `MarketDataPort`; retain REST polling as fallback.
3. Normalize streamed and REST data into the same snapshot and run the unchanged decision pipeline.
4. If no, remove the scaffolds after documenting the decision.

### Release and rollback strategy

- Ship each phase behind a configuration flag and retain the previous path for at least one release.
- In shadow mode, calculate both paths but render only the legacy result; log field differences without placing orders (the application remains decision-support only).
- Define acceptance thresholds for exact categorical parity (side/status/veto) and numeric tolerances (scores/plans).
- Back up SQLite before migration, use additive schema changes first, and keep migrations idempotent.
- Roll back by switching the application-service feature flag, not by reverting stored user history.
- The migration is complete only when the active dashboard—not merely the alternate smoke test—uses the canonical provider, pipeline, safety policy, and view model with no functional regression.
