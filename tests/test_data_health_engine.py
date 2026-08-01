from datetime import datetime

import pytest

import engines.data_health_engine as data_health_module
from engines.data_health_engine import DataHealthEngine
from itos_platform import MarketSnapshot


COMPLETE_INTELLIGENCE = {
    "state": "balanced",
    "spot": 100,
    "atm": 100,
    "support": 95,
    "resistance": 105,
}
VALID_RECOMMENDATION = {"side": "CE", "status": "WATCH"}


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 8, 1, 12, 0, 0)
        return value.replace(tzinfo=tz) if tz is not None else value


@pytest.fixture(autouse=True)
def fixed_health_clock(monkeypatch):
    monkeypatch.setattr(data_health_module, "datetime", FixedDateTime)


def _last_refresh(*, minutes_ago=0):
    return "11:55:00" if minutes_ago else "12:00:00"


@pytest.mark.parametrize(
    "overrides",
    [
        {"recommendation": {}},
        {"recommendation": {"side": "CE"}},
        {"recommendation": VALID_RECOMMENDATION},
        {"option_result": {}},
        {"intelligence": {"state": "balanced"}},
        {"last_refresh": _last_refresh(minutes_ago=5)},
    ],
    ids=[
        "empty-recommendation",
        "incomplete-recommendation",
        "minimum-valid-recommendation",
        "missing-option-chain",
        "missing-intelligence-fields",
        "stale-last-refresh",
    ],
)
def test_legacy_and_snapshot_inputs_have_identical_results(overrides):
    legacy = {
        "option_result": {"chain": list(range(6))},
        "intelligence": COMPLETE_INTELLIGENCE,
        "recommendation": VALID_RECOMMENDATION,
        "last_refresh": _last_refresh(),
    }
    legacy.update(overrides)

    legacy_result = DataHealthEngine().analyze(legacy)
    snapshot_result = DataHealthEngine().analyze(MarketSnapshot.from_legacy(legacy))

    assert snapshot_result.score == legacy_result.score
    assert snapshot_result.vote == legacy_result.vote
    assert snapshot_result.confidence == legacy_result.confidence
    assert snapshot_result.explanation == legacy_result.explanation
    assert snapshot_result.metadata == legacy_result.metadata
    assert snapshot_result.metadata["flags"] == legacy_result.metadata["flags"]


def test_data_health_scenarios_emit_expected_flags():
    base = {
        "option_result": {},
        "intelligence": {"state": "balanced"},
        "recommendation": {"side": "CE"},
        "last_refresh": _last_refresh(minutes_ago=5),
    }

    result = DataHealthEngine().analyze(base)

    assert {
        "OPTION_CHAIN_MISSING",
        "INTELLIGENCE_FIELDS_MISSING",
        "RECOMMENDATION_MISSING",
        "DATA_STALE",
    }.issubset(result.metadata["flags"])
