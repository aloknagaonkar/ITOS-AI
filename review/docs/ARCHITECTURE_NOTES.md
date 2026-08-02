# Architecture Notes

The engine accepts `DecisionContext` or a deliberately separate legacy mapping adapter. It reads only the point-in-time snapshot and already-computed typed context; it has no repository, Streamlit, persistence or recommendation dependency. Pipeline placement follows market location, volume structure, positioning, compression context and `FalseBreakoutEngine`. One frozen result is stored in `DecisionContext`, `PipelineResults`, and the dashboard compatibility mapping by identity.

Compression is represented by a small frozen compatibility contract because the current branch did not contain Sprint 14's typed module. Its unavailable default makes no manipulation inference and does not change any pre-existing formula.
