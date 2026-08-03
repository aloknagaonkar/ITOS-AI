# Known Issues

- Streamlit executes the pipeline synchronously. A cancellation request is honored after the current atomic per-date provider/service request; Python cannot interrupt an already in-flight provider call safely.
- Exchange holiday data is not bundled. Weekends are skipped; ambiguous weekday empty responses remain Provider No Data rather than being falsely labelled exchange holidays.
- The current option provider result exposes aggregate expiry/contract success and failures. Per-date option status is accurate because orchestration invokes it per date; CE/PE and OI/volume coverage are displayed only when a provider result supplies those fields.
- Manual browser interaction validation remains required in the deployment environment.
