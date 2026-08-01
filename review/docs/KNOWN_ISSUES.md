# Known Issues

- Swing fallback uses deterministic interior extrema, not a pivot-strength or session-aware swing algorithm.
- Transition history is inferred from candles in the configured window; it is not persisted.
- `CONFLICTING_STRUCTURE` is reserved for a future normalized structure contract and is not emitted from today's heterogeneous metadata.
- Staleness is assessed only when a parseable candle/captured timestamp is available.
- Volume is intentionally not interpreted in Sprint 11.
