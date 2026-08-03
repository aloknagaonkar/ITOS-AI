# Known Issues

- Streamlit runs `orchestrator.run()` synchronously, so normal users cannot reliably submit an interactive cancellation while that call blocks. The normal cancellation button is therefore hidden. The orchestration boundary retains programmatic cancellation checks for future chunked/background execution and safely checkpoints after an atomic per-date request.
- Exchange holiday data is not bundled. Weekends are skipped; ambiguous weekday empty responses remain Provider No Data rather than being falsely labelled exchange holidays.
- The current option provider result exposes aggregate expiry/contract success and failures. Per-date option status is accurate because orchestration invokes it per date; CE/PE and OI/volume coverage are displayed only when a provider result supplies those fields.
- Manual browser interaction validation remains required in the deployment environment.
