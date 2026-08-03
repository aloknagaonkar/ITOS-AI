# Known Issues
- Manual browser UI validation remains required.
- Historical movement fields are unavailable in the current compact SQLite index row and therefore remain `None`; the service never fabricates them.
- Parquet export is available only when a supported pandas parquet engine is installed.
- Live/replay sources require a frozen indexed Historical Trade ID in the v1 workspace; absence is non-blocking and diagnostic.

## Sprint 18.4F.1
Manual browser validation with a user-supplied read-only Upstox token remains required. Historical expired-option availability depends on the broker entitlement and endpoint coverage.
