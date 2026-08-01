# Files Changed — Sprint 9 Test Correction

| File | Reason | Architectural impact | Backward compatibility |
|---|---|---|---|
| `tests/test_decision_pipeline.py` | Replace positional-count assumptions with unique, keyword-bound field sentinels | Keeps typed result-contract characterization resilient to reviewed fields | Test-only; legacy alias identity remains verified |
| `tests/test_institutional_metrics.py` | Correct OI-weighted delta expectation and cover configured weighting/sign/zero-weight behavior | Precisely characterizes the unchanged Greek aggregation formula | Test-only; production formulas unchanged |
| `review/source/tests/test_decision_pipeline.py` | Mirror the modified pipeline test | Updates source review package | Review-only |
| `review/source/tests/test_institutional_metrics.py` | Mirror the modified metrics test | Updates source review package | Review-only |
| `review/docs/TEST_REPORT.md` | Record corrected coverage and local pytest requirement | Audit documentation | None |
| `review/docs/FILES_CHANGED.md` | Enumerate this follow-up patch | Audit documentation | None |
| `review/docs/SPRINT_SUMMARY.md` | Record review-follow-up outcome | Audit documentation | None |
| `review/docs/SELF_REVIEW.md` | Record formula-preservation review | Audit documentation | None |
| `review/docs/BUILD_LOG.txt` | Capture permitted validation output | Audit documentation | None |
