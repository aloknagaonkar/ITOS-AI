# Historical Replay UX Rules

## Workspace model
The top-level selector offers Analyst Dashboard and Historical Replay. LIVE defaults to the unchanged Analyst Dashboard. Non-live modes prohibit live acquisition and fallback.

## Mode controls
Data Mode uses the typed `DataMode` enum: LIVE, HISTORICAL_REPLAY, or SAMPLE_DATA. A change clears incompatible `replay_*` artifacts while preserving unrelated live state.

## Replay controls
Underlying, instrument key, trading date, replay time, supported candle interval, optional expiry, warm-up status, option-snapshot request, and Run Replay are explicit inputs. `ReplayRequest.validate` enforces session bounds and configuration.

## Next/previous candle behavior
Navigation uses actual completed candle timestamps. It disables at boundaries and creates a fresh immutable request; it never increments arbitrary wall-clock time.

## Jump-to-time behavior
Jump resolves the nearest completed candle at or before the requested time and displays both requested and resolved timestamps.

## Session-state contract
All state is prefixed `replay_*`: mode, workspace, request, timestamp, candle index/timestamps, frozen result, history points, outcome, error, error count, requested timestamp, and last successful metadata. Reset does not touch persistent caches or live keys.

## Replay banner and completeness panel
Banner and diagnostics render provider-owned `ReplayMetadata`, including sources, cutoffs, option status, exclusions, cleanup counts, warm-up/session counts, flags, and explanations.

## Frozen decision summary
A replay result is replaced only after an explicit successful execution. It represents the current replay decision and introduces no execution state.

## Decision timeline
Only explicitly executed points are accepted. Duplicate timestamps deterministically replace the same point; values are chronological and bounded by configuration. Future outcome fields never enter a point.

## Outcome separation
Outcome data is hidden until requested. Immutable `ReplayOutcome` is built from a separate future frame and is labelled “Not used in the replay decision.” It never enters Compression, Manipulation, Institutional Evidence, Decision Confidence, Validation, or Ranking.

## Sample-mode warning
SAMPLE_DATA uses `SampleDataProvider` and prominently states “SAMPLE DATA — NOT FOR TRADING” and “Deterministic development fixture.”

## Live-mode preservation
The existing Analyst Dashboard route, behavior, sections, order, exports, downloads, session keys, and CE/PE/WAIT semantics remain unchanged.

## Error handling
Expected validation/provider/data errors are rendered as safe text. Replay never silently falls back to LIVE.

## Deferred work
The Execution Decision Engine and its states are deferred to Sprint 18.5. Explainable Navigation is deferred to Sprint 18.6. The Executive Trade Cockpit is deferred to Sprint 19.
