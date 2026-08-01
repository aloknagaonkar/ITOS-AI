from types import SimpleNamespace

import pandas as pd
import pytest

from engines.stability_engine import RecommendationStabilityEngine
from itos_platform import DecisionContext, MarketSnapshot


def _context(legacy):
    return DecisionContext(
        market_snapshot=MarketSnapshot(option_result={}, intelligence={}),
        recommendation=legacy.get("recommendation", {}),
        engine_results={"market_cycle": legacy.get("cycle_result")},
        confidence_history=legacy.get("confidence_history"),
        phase_history=legacy.get("phase_history"),
        runtime_configuration={"minimum_stability": 70.0},
    )


def _assert_identical(left, right):
    assert left.score == right.score
    assert left.vote == right.vote
    assert left.confidence == right.confidence
    assert left.explanation == right.explanation
    assert left.metadata == right.metadata
    for key in (
        "stability_score",
        "label",
        "trend",
        "direction_changes",
        "passed",
    ):
        assert left.metadata[key] == right.metadata[key]


@pytest.mark.parametrize(
    "history,phase_history,cycle",
    [
        (pd.DataFrame({"side": ["CE", "CE", "PE"], "calibrated_confidence": [72, 74, 68], "consensus_agreeing": [3, 4, 2], "consensus_total": [4, 4, 4]}), pd.DataFrame({"phase": ["Accumulation", "Accumulation"]}), SimpleNamespace(metadata={"manipulation_score": 12})),
        (pd.DataFrame(), pd.DataFrame(), None),
        (pd.DataFrame({"side": ["CE"]}), pd.DataFrame({"phase": ["Unknown"]}), None),
        (pd.DataFrame({"unexpected": ["bad", None], "calibrated_confidence": ["bad", None]}), "malformed", SimpleNamespace(metadata={})),
        (pd.DataFrame({"side": ["PE", "CE", "PE", "CE"], "calibrated_confidence": [50, 60, 55, 70]}), pd.DataFrame(), SimpleNamespace(metadata={})),
        (pd.DataFrame({"side": ["CE"] * 5, "calibrated_confidence": [80] * 5}), pd.DataFrame({"phase": ["Expansion"] * 4}), SimpleNamespace(metadata={})),
        (pd.DataFrame({"side": ["CE", "CE"], "calibrated_confidence": [60, 62]}), pd.DataFrame(), SimpleNamespace()),
    ],
    ids=["complete-history", "empty-history", "insufficient-history", "malformed-history", "direction-changes", "stable-recommendations", "missing-cycle-metadata"],
)
def test_legacy_and_typed_context_have_exact_parity(history, phase_history, cycle):
    legacy = {
        "recommendation": {"side": "CE", "confidence": 75},
        "confidence_history": history,
        "phase_history": phase_history,
        "cycle_result": cycle,
    }
    engine = RecommendationStabilityEngine()
    _assert_identical(engine.analyze(legacy), engine.analyze(_context(legacy)))


def test_cached_context_reuse_is_deterministic_and_does_not_rebuild_snapshot():
    legacy = {"recommendation": {"side": "PE", "confidence": 64}, "confidence_history": pd.DataFrame(), "phase_history": pd.DataFrame(), "cycle_result": None}
    context = _context(legacy)
    engine = RecommendationStabilityEngine()
    first = engine.analyze(context)
    second = engine.analyze(context)
    _assert_identical(first, second)
    assert context.market_snapshot is context.market_snapshot


def test_stable_pe_recommendations_have_legacy_and_context_parity():
    legacy = {
        "recommendation": {"side": "PE", "confidence": 82},
        "confidence_history": pd.DataFrame(
            {
                "side": ["PE"] * 5,
                "calibrated_confidence": [80, 81, 82, 83, 82],
            }
        ),
        "phase_history": pd.DataFrame({"phase": ["Expansion"] * 4}),
        "cycle_result": SimpleNamespace(metadata={}),
    }

    engine = RecommendationStabilityEngine()
    _assert_identical(engine.analyze(legacy), engine.analyze(_context(legacy)))


def test_configured_minimum_threshold_has_legacy_and_context_parity():
    legacy = {
        "recommendation": {"side": "CE", "confidence": 75},
        "confidence_history": pd.DataFrame(),
        "phase_history": pd.DataFrame(),
    }
    engine = RecommendationStabilityEngine(minimum_stability=40)
    legacy_result = engine.analyze(legacy)
    context_result = engine.analyze(_context(legacy))

    _assert_identical(legacy_result, context_result)
    assert legacy_result.metadata["minimum_required"] == 40
    assert legacy_result.metadata["passed"] is True
    assert legacy_result.vote == "CE"
