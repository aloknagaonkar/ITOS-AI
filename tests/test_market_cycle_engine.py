import pandas as pd
import pytest

from engines.market_cycle_engine import MarketCycleEngine
from itos_platform import DecisionContext, MarketSnapshot


def _candles(count=12):
    rows = []
    for index in range(count):
        close = 100.0 + index * 0.7
        rows.append(
            {
                "open": close - 0.3,
                "high": close + 0.5,
                "low": close - 0.6,
                "close": close,
                "volume": 1000 + index * 20,
            }
        )
    return pd.DataFrame(rows)


def _legacy(*, candles=None, option_result=None):
    frame = _candles() if candles is None else candles
    return {
        "option_result": (
            {"summary": {"call_oi_change": 120, "put_oi_change": 250}}
            if option_result is None
            else option_result
        ),
        "intelligence": {
            "score": 2.4,
            "price": {
                "candles": frame,
                "close": 108,
                "vwap": 105,
                "ema9": 107,
                "ema21": 104,
            },
        },
        "institutional": {"primary_strength": 38},
        "historical_candles": frame,
        "timestamps": {"last_refresh": "10:00:00"},
        "data_quality": {"source": "complete"},
    }


def _assert_parity(legacy):
    legacy_result = MarketCycleEngine().analyze(legacy)
    snapshot = MarketSnapshot.from_legacy(legacy)
    typed_result = MarketCycleEngine(
        institutional_compatibility=legacy.get("institutional")
    ).analyze(snapshot)

    assert typed_result.score == legacy_result.score
    assert typed_result.vote == legacy_result.vote
    assert typed_result.confidence == legacy_result.confidence
    assert typed_result.explanation == legacy_result.explanation
    assert typed_result.metadata == legacy_result.metadata
    assert typed_result.metadata["phase"] == legacy_result.metadata["phase"]
    assert typed_result.metadata["trade_allowed"] == legacy_result.metadata["trade_allowed"]
    assert typed_result.metadata.get("manipulation_score") == legacy_result.metadata.get(
        "manipulation_score"
    )
    return typed_result


@pytest.mark.parametrize(
    "legacy",
    [
        pytest.param(_legacy(), id="complete-market-data"),
        pytest.param(_legacy(candles=pd.DataFrame()), id="missing-candle-data"),
        pytest.param(_legacy(option_result={}), id="missing-option-chain-data"),
        pytest.param(_legacy(candles=_candles(7)), id="insufficient-history"),
    ],
)
def test_legacy_and_market_snapshot_results_are_identical(legacy):
    _assert_parity(legacy)


def test_insufficient_history_behavior_remains_blocked_and_unknown():
    result = _assert_parity(_legacy(candles=_candles(7)))

    assert result.vote == "WAIT"
    assert result.metadata == {
        "phase": "Unknown",
        "phase_confidence": 20.0,
        "probabilities": {"Unknown": 100.0},
        "trade_allowed": False,
    }


@pytest.mark.parametrize(
    "option_result,intelligence",
    [
        (None, None),
        ({"summary": None}, {"score": "bad", "price": None}),
        ({"summary": {"call_oi_change": object()}}, {"price": {"candles": "bad"}}),
        ({}, {"price": {"candles": pd.DataFrame({"close": range(10)})}}),
    ],
)
def test_malformed_optional_fields_degrade_safely(option_result, intelligence):
    snapshot = MarketSnapshot(
        option_result=option_result,  # type: ignore[arg-type]
        intelligence=intelligence,  # type: ignore[arg-type]
        historical_candles=None,
        timestamps={"last_refresh": None},
        data_quality={"flags": None},
    )

    result = MarketCycleEngine().analyze(snapshot)

    assert result.vote == "WAIT"
    assert result.metadata["phase"] == "Unknown"
    assert result.metadata["trade_allowed"] is False


def test_decision_context_carries_institutional_compatibility_without_snapshot_mutation():
    legacy = _legacy()
    snapshot = MarketSnapshot.from_legacy(legacy)
    context = DecisionContext(
        market_snapshot=snapshot,
        historical_repositories={"institutional": legacy["institutional"]},
    )

    context_result = MarketCycleEngine().analyze(context)
    legacy_result = MarketCycleEngine().analyze(legacy)

    assert context.market_snapshot is snapshot
    assert context_result.metadata == legacy_result.metadata
    assert context_result.explanation == legacy_result.explanation
