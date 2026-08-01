from dataclasses import FrozenInstanceError

import pytest

from itos_platform import (
    DecisionContext,
    MarketSnapshot,
    recommendation_is_available,
)


def test_market_snapshot_encapsulates_market_inputs():
    candles = object()
    snapshot = MarketSnapshot(
        option_result={"chain": [1, 2]},
        intelligence={"state": "balanced"},
        historical_candles=candles,
        timestamps={"last_refresh": "10:11:12"},
        selected_instrument="NIFTY",
        expiry="2026-08-06",
        timeframe=5,
        data_quality={"source": "live"},
    )

    assert snapshot.historical_candles is candles
    assert snapshot.selected_instrument == "NIFTY"
    assert snapshot.timestamps["last_refresh"] == "10:11:12"


def test_market_snapshot_is_frozen():
    snapshot = MarketSnapshot(option_result={}, intelligence={})

    with pytest.raises(FrozenInstanceError):
        snapshot.expiry = "2026-08-13"


def test_legacy_adapter_preserves_data_health_inputs():
    snapshot = MarketSnapshot.from_legacy(
        {
            "option_result": {"chain": [1]},
            "intelligence": {"state": "balanced"},
            "recommendation": {"side": "CE", "status": "WATCH"},
            "last_refresh": "10:11:12",
            "underlying": "BANKNIFTY",
        }
    )

    assert snapshot.data_quality["recommendation_available"] is True
    assert snapshot.timestamps["last_refresh"] == "10:11:12"
    assert snapshot.selected_instrument == "BANKNIFTY"


@pytest.mark.parametrize(
    ("recommendation", "expected"),
    [
        ({}, False),
        ({"side": "CE"}, False),
        ({"side": "CE", "status": "WATCH"}, True),
        ("not a mapping", False),
    ],
)
def test_recommendation_availability_requires_minimum_mapping(
    recommendation, expected
):
    assert recommendation_is_available(recommendation) is expected
    snapshot = MarketSnapshot.from_legacy({"recommendation": recommendation})
    assert snapshot.data_quality["recommendation_available"] is expected


def test_legacy_adapter_prefers_production_historical_candle_key():
    production_candles = object()
    legacy_candles = object()

    snapshot = MarketSnapshot.from_legacy(
        {
            "historical_pattern_candles": production_candles,
            "historical_candles": legacy_candles,
        }
    )

    assert snapshot.historical_candles is production_candles


def test_decision_context_is_frozen_and_holds_runtime_dependencies():
    snapshot = MarketSnapshot(option_result={}, intelligence={})
    context = DecisionContext(
        market_snapshot=snapshot,
        historical_repositories={"snapshots": object()},
        configuration={"minimum_confidence": 70},
        session_state={"authenticated": True},
        runtime_settings={"dry_run": True},
    )

    assert context.market_snapshot is snapshot
    with pytest.raises(FrozenInstanceError):
        context.market_snapshot = MarketSnapshot(option_result={}, intelligence={})
