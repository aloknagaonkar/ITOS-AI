# Test Report
pytest not executed by Codex — local validation required.

Codex validation is restricted to `python -m py_compile <all modified Python files>`
and `git diff --check`. Local validation must run `python -m pytest -q` and
`streamlit run app.py`.
