# Architecture Notes

## Typed Boundary
`PhaseTransitionEngine.analyze` now prefers `DecisionContext`. A single private
`_adapt_input` method converts legacy mappings to that contract. Both call paths
then execute the same transition calculation.

## Data Ownership
- `MarketSnapshot` remains point-in-time market data only.
- `DecisionContext.cycle_result` and its mirrored `engine_results["market_cycle"]`
  provide the market-cycle engine output to downstream decision engines.
- Legacy-only inline `cycle` metadata is held in runtime configuration by the
  compatibility adapter rather than contaminating the market snapshot.

## Pipeline Identity
The application service constructs exactly one `MarketSnapshot` and one
`DecisionContext`. Market-cycle and data-health receive the former; stability and
phase-transition receive the latter. Neither contract is reconstructed later.
