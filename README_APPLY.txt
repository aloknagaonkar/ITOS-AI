Historical Option Download Idempotency Update

Replace the matching files in the repository while preserving paths.

Changes:
- Reuses stored historical option coverage on repeated runs.
- Persists PARTIAL and UNAVAILABLE terminal states in the Market Lake manifest.
- Retries transient failures because they are not cached as unavailable.
- Adds a Force re-download historical options checkbox.
- Displays Existing and Previously Unavailable option statuses.
- Adds repeat-run and force-refresh tests.

Validate:
python -m py_compile app.py itos_platform\historical_options.py itos_platform\historical_analysis_orchestrator.py itos_platform\market_lake.py ui\historical_analytics_workspace.py
pytest tests\test_historical_options_and_live_capture.py -q
pytest tests\test_historical_analysis_orchestrator.py -q
pytest -q
