# Known Issues

- The current branch has no full Compression Intelligence engine. Sprint 15 therefore consumes a typed unavailable/default compatibility result; genuine Sprint 14 output can be supplied through `DecisionContext` without changing this engine.
- Candle inputs do not consistently expose validated swing-high/swing-low identities. The first version uses validated support/resistance supplied by Market Location.
- Missing timestamps cannot be labelled stale; they remain usable with other quality flags rather than being guessed.
- UI execution and full pytest validation are deferred to the required local validation workflow.
