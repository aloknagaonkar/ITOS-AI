# Known Issues
- Exchange holiday detection relies on an empty provider response; no exchange calendar is bundled.
- Historical option persistence is an interface only until a licensed snapshot source is configured.
- JSON is used instead of parquet to avoid adding a heavy optional dependency.
- Full replay UX and outcome evaluation are deferred to Sprint 18.4B.
