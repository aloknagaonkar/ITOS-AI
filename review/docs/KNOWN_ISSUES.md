# Known Issues
- The graph is intentionally preliminary token overlap, not Sprint 18.4F similarity scoring.
- Statistics recomputation is bounded by configured maximum query size; callers should partition very large datasets.
- Automatic live/enrichment index hooks are configuration-ready but disabled by default to avoid changing existing capture behavior.
- Manual UI validation remains required; no normal UI files were changed.
