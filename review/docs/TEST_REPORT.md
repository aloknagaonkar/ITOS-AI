# Test Report

pytest not executed by Codex — local validation required.

## Sprint 9 follow-up

- Reworked the `PipelineResults` mapping test to create a unique sentinel per authoritative result field, use keyword construction, include `institutional_metrics`, and retain identity checks for `ice_result` and `smi_result`.
- Corrected deterministic OI-weighted delta expectations to `26 / 60` and `-26 / 60`.
- Added explicit OI-versus-volume Greek weighting, sign-preservation, and zero-weight safety coverage.

Run locally: `python -m pytest -q`.
