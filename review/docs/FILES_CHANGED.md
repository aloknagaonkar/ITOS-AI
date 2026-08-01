# Files Changed — Sprint 7 Malformed-Input Follow-up

| Filename | Reason changed | Architectural impact | Backward compatibility impact |
|---|---|---|---|
| `engines/core_intelligence.py` | Normalize optional nested mappings in Market Regime, SMI, and Market Energy before `.get()`. | Adds a shared normalization boundary; calculation paths are unchanged. | Valid mapping inputs produce unchanged results; malformed inputs now degrade safely. |
| `engines/institutional_flow.py` | Normalize Early Warning recommendation and metadata inputs. | Strengthens the existing adapter boundary without changing decision logic. | Valid inputs and metadata schema are unchanged; malformed values no longer raise. |
| `tests/test_market_state_context.py` | Expand malformed optional mapping characterization. | Protects all four Sprint 7 engine boundaries. | Retains typed/legacy valid-input parity coverage. |
| `review/docs/BUILD_LOG.txt` | Capture complete authorized validation output. | Documentation only. | None. |
| `review/docs/TEST_REPORT.md` | Record validation scope and required local pytest. | Documentation only. | None. |
| `review/docs/KNOWN_ISSUES.md` | Record remaining validation limitation. | Documentation only. | None. |
| `review/docs/FILES_CHANGED.md` | Inventory this follow-up. | Documentation only. | None. |
| `review/source/engines/core_intelligence.py` | Refresh production source review copy. | Review artifact only. | None. |
| `review/source/engines/institutional_flow.py` | Refresh production source review copy. | Review artifact only. | None. |
| `review/source/tests/test_market_state_context.py` | Refresh test source review copy. | Review artifact only. | None. |
