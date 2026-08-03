# Known Issues

- Streamlit executes the workflow synchronously; cancellation is observed at safe stage boundaries rather than interrupting an in-flight provider request.
- Exchange holiday data is not bundled. Weekends are skipped; ambiguous weekday no-data responses remain provider/unknown conditions rather than being falsely called holidays.
- Historical option completeness depends on provider authentication, contract discovery, and endpoint availability; candle-only analysis remains supported.
- Manual browser validation remains required in the deployment environment.
