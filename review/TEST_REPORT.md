# Test Report

- **Python Version:** 3.14.4
- **Operating System:** Linux 6.12.13 x86_64
- **Commands Executed:**
  - `python -m py_compile dashboard_application_service.py engines/stability_engine.py engines/data_health_engine.py itos_platform/decision_context.py itos_platform/__init__.py tests/test_dashboard_application_service.py tests/test_stability_typed_context.py`
  - `git diff --check`
  - `python -m pytest -q`
- **Tests Collected:** 0 (collection blocked by missing `pandas`)
- **Passed:** 0
- **Failed:** 0 test failures; 2 collection errors
- **Skipped:** 0
- **Warnings:** Project dependencies are absent. `python -m pip install -r requirements.txt` was attempted, but the configured package-index tunnel returned HTTP 403.
- **Total Runtime:** 0.27 seconds for pytest
- **Coverage:** Not available because collection could not complete

See `BUILD_LOG.txt` for complete required-command output.
