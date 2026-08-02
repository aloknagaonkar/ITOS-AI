# Known Issues
- Exchange holiday detection relies on an empty provider response; no exchange calendar is bundled.
- Historical option persistence is an interface only until a licensed snapshot source is configured.
- JSON is used instead of parquet to avoid adding a heavy optional dependency.
- Full replay UX and outcome evaluation are deferred to Sprint 18.4B.
- Pytest was not run by Codex; the complete suite requires developer local validation.
- Candle-only and sample snapshots fail closed at the current application boundary
  when no recommendation inputs exist; they do not produce a live-backed ranking.
