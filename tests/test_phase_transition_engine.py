from types import SimpleNamespace

import pytest

from engines.institutional_intelligence import PhaseTransitionEngine
from itos_platform import DecisionContext, MarketSnapshot


def _context(cycle_result=None):
    return DecisionContext(
        market_snapshot=MarketSnapshot(option_result={}, intelligence={}),
        cycle_result=cycle_result,
    )


def _cycle(phase, probabilities):
    return SimpleNamespace(metadata={"phase": phase, "probabilities": probabilities})


def _assert_parity(legacy, typed):
    left = PhaseTransitionEngine().analyze(legacy)
    right = PhaseTransitionEngine().analyze(typed)
    assert left.score == right.score
    assert left.vote == right.vote
    assert left.confidence == right.confidence
    assert left.explanation == right.explanation
    assert left.metadata == right.metadata
    for key in ("current_phase", "next_phase", "transition_probability"):
        assert left.metadata[key] == right.metadata[key]
    assert left.metadata["transition_state"] == right.metadata["transition_state"]
    return left


@pytest.mark.parametrize(
    ("phase", "vote", "next_phase"),
    [
        ("Accumulation", "CE", "Bullish Expansion"),
        ("Distribution", "PE", "Bearish Expansion"),
        ("Compression", "WAIT", "Accumulation / Distribution"),
        ("Bullish Expansion", "CE", "Distribution"),
        ("Bearish Expansion", "PE", "Compression / Accumulation"),
        ("Manipulation", "WAIT", "Directional Reversal / Expansion"),
        ("Unrecognized", "WAIT", "Unknown"),
    ],
)
def test_typed_and_legacy_phase_parity(phase, vote, next_phase):
    cycle = _cycle(phase, {phase: 64, "Compression": 36})
    result = _assert_parity({"cycle_result": cycle}, _context(cycle))
    assert result.vote == vote
    assert result.metadata["current_phase"] == phase
    assert result.metadata["next_phase"] == next_phase


@pytest.mark.parametrize(
    "legacy",
    [
        {},
        {"cycle_result": SimpleNamespace(metadata=None)},
        {"cycle_result": SimpleNamespace(metadata={"phase": None, "probabilities": None})},
        {"cycle_result": SimpleNamespace(metadata={"phase": "Compression", "probabilities": {"Compression": "bad", "Other": float("nan")}})},
        {"cycle_result": SimpleNamespace(metadata={"phase": "Accumulation", "probabilities": "malformed"})},
    ],
)
def test_missing_and_malformed_values_degrade_safely_with_parity(legacy):
    cycle = legacy.get("cycle_result")
    result = _assert_parity(legacy, _context(cycle))
    assert 0 <= result.score <= 100
    assert result.confidence == result.score


def test_legacy_cycle_metadata_fallback_has_typed_parity():
    metadata = {"phase": "Distribution", "probabilities": {"Distribution": 52, "Accumulation": 48}}
    legacy = {"cycle": metadata}
    typed = DecisionContext(
        market_snapshot=MarketSnapshot(option_result={}, intelligence={}),
        runtime_configuration={"cycle": metadata},
    )
    result = _assert_parity(legacy, typed)
    assert result.metadata["transition_state"] == "TRANSITIONING"


def test_cached_repeated_execution_is_stable():
    cycle = _cycle("Bullish Expansion", {"Bullish Expansion": 72, "Distribution": 28})
    context = _context(cycle)
    first = PhaseTransitionEngine().analyze(context)
    second = PhaseTransitionEngine().analyze(context)
    assert (first.score, first.vote, first.explanation, first.metadata) == (
        second.score, second.vote, second.explanation, second.metadata
    )
