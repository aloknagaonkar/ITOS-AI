from types import SimpleNamespace

import pandas as pd
import pytest

from engines import (
    InstitutionalConfidenceEngine,
    InstitutionalDecisionMatrixEngine,
    InstitutionalFlowEngine,
    InstitutionalRadarEngine,
)
from itos_platform import DecisionContext, MarketSnapshot
from itos_platform.institutional_metrics import InstitutionalMetricsEngine


def _assert_result_parity(legacy, typed):
    assert typed.engine == legacy.engine
    assert typed.score == legacy.score
    assert typed.vote == legacy.vote
    assert typed.confidence == legacy.confidence
    assert typed.explanation == legacy.explanation
    assert typed.metadata == legacy.metadata


def _result(score, vote="CE", **metadata):
    return SimpleNamespace(score=score, vote=vote, metadata=metadata)


def _history():
    return pd.DataFrame({
        "captured_at": pd.date_range("2026-07-31 09:15", periods=5, freq="min"),
        "call_oi": [100, 110, 125, 140, 160],
        "put_oi": [100, 120, 145, 175, 210],
        "spot": [100, 101, 102, 103, 104],
        "atm_iv": [12, 12.1, 12.3, 12.5, 12.8],
        "pcr_oi": [1, 1.02, 1.05, 1.08, 1.1],
        "call_oi_change": [0, 10, 15, 15, 20],
        "put_oi_change": [0, 20, 25, 30, 35],
    })


@pytest.mark.parametrize("side", ["CE", "PE"])
def test_radar_legacy_and_context_parity(side):
    recommendation = {"side": side}
    option = {"summary": {"call_oi_change": 120, "put_oi_change": 180}}
    intelligence = {"bullish_probability": 68, "bearish_probability": 32}
    institutional = {"primary_strength": 44}
    legacy_input = {
        "recommendation": recommendation, "option_result": option,
        "intelligence": intelligence, "institutional": institutional,
    }
    context = DecisionContext(
        MarketSnapshot(option, intelligence), recommendation=recommendation,
        institutional=institutional,
    )
    _assert_result_parity(
        InstitutionalRadarEngine().analyze(legacy_input),
        InstitutionalRadarEngine().analyze(context),
    )


@pytest.mark.parametrize("history", [_history(), pd.DataFrame()], ids=["complete", "empty"])
def test_flow_legacy_and_context_parity(history):
    recommendation = {"side": "CE"}
    legacy_input = {"history": history, "strike_history": None, "recommendation": recommendation}
    context = DecisionContext(
        MarketSnapshot({}, {}), recommendation=recommendation,
        decision_history=history, strike_history=None,
    )
    _assert_result_parity(
        InstitutionalFlowEngine().analyze(legacy_input),
        InstitutionalFlowEngine().analyze(context),
    )


def test_decision_matrix_and_confidence_legacy_context_parity():
    recommendation = {
        "side": "CE", "confirmed": True, "confidence": 81,
        "component_scores": {"Trend": 80, "OI / Institutional Flow": 76,
                             "Volume": 70, "Greeks": 68, "Liquidity": 75,
                             "Risk / Reward": 72},
    }
    results = {
        "market_cycle": _result(78), "institutional_footprint": _result(74),
        "institutional_confirmation": _result(82, status="CONFIRMED"),
        "candle_dna": _result(71), "pattern_recognition": _result(77),
        "false_breakout": _result(18),
    }
    context = DecisionContext(
        MarketSnapshot({}, {"bullish_probability": 70}),
        recommendation=recommendation, engine_results=results,
    )
    matrix_legacy = {
        "recommendation": recommendation, "intelligence": context.market_snapshot.intelligence,
        "cycle_result": results["market_cycle"],
        "footprint_result": results["institutional_footprint"],
        "confirmation_result": results["institutional_confirmation"],
        "candle_dna_result": results["candle_dna"],
        "pattern_result": results["pattern_recognition"],
        "false_breakout_result": results["false_breakout"],
    }
    legacy_matrix = InstitutionalDecisionMatrixEngine().analyze(matrix_legacy)
    typed_matrix = InstitutionalDecisionMatrixEngine().analyze(context)
    _assert_result_parity(legacy_matrix, typed_matrix)

    flow = InstitutionalFlowEngine().analyze({
        "history": _history(), "strike_history": None, "recommendation": recommendation,
    })
    context.engine_results.update(
        institutional_flow=flow, institutional_decision_matrix=typed_matrix
    )
    confidence_legacy = dict(
        recommendation=recommendation, flow_result=flow,
        confirmation_result=results["institutional_confirmation"],
        cycle_result=results["market_cycle"], candle_dna_result=results["candle_dna"],
        pattern_result=results["pattern_recognition"], decision_matrix_result=typed_matrix,
    )
    _assert_result_parity(
        InstitutionalConfidenceEngine().analyze(confidence_legacy),
        InstitutionalConfidenceEngine().analyze(context),
    )


@pytest.mark.parametrize("bad_history", [None, object(), pd.DataFrame({"captured_at": [1]})])
def test_flow_malformed_history_degrades_to_wait(bad_history):
    result = InstitutionalFlowEngine().analyze({"history": bad_history, "recommendation": None})
    assert result.vote == "WAIT"
    assert result.score == 25
    assert result.metadata["flow_state"] == "WARMING UP"


def test_all_migrated_adapters_reuse_the_same_metrics_instance():
    history = _history().assign(timestamp=lambda frame: frame["captured_at"])
    chain = pd.DataFrame({
        "strike": [99, 100, 101], "call_oi": [100, 120, 90],
        "put_oi": [90, 130, 140], "call_oi_change": [10, 20, 30],
        "put_oi_change": [20, 30, 40], "call_volume": [500, 600, 700],
        "put_volume": [600, 700, 800],
    })
    snapshot = MarketSnapshot({"chain": chain, "summary": {"spot": 100}}, {})
    base = DecisionContext(snapshot, decision_history=history)
    metrics = InstitutionalMetricsEngine().analyze(base)
    context = DecisionContext(snapshot, decision_history=history,
                              institutional_metrics=metrics)

    adapters = (
        InstitutionalRadarEngine._adapt_input,
        InstitutionalFlowEngine._adapt_input,
        InstitutionalConfidenceEngine._adapt_input,
        InstitutionalDecisionMatrixEngine._adapt_input,
    )
    assert all(adapter(context)["institutional_metrics"] is metrics for adapter in adapters)


def test_radar_typed_metrics_matches_equivalent_legacy_totals():
    chain = pd.DataFrame({
        "strike": [100], "call_oi": [100], "put_oi": [120],
        "call_oi_change": [40], "put_oi_change": [60],
        "call_volume": [1000], "put_volume": [1200],
    })
    recommendation = {"side": "CE"}
    intelligence = {"bullish_probability": 60, "bearish_probability": 40}
    option = {"chain": chain, "summary": {"spot": 100,
              "call_oi_change": 40, "put_oi_change": 60}}
    raw_context = DecisionContext(MarketSnapshot(option, intelligence),
                                  recommendation=recommendation)
    metrics = InstitutionalMetricsEngine().analyze(raw_context)
    typed_context = DecisionContext(raw_context.market_snapshot,
                                    recommendation=recommendation,
                                    institutional_metrics=metrics)
    legacy = InstitutionalRadarEngine().analyze({
        "recommendation": recommendation, "option_result": option,
        "intelligence": intelligence,
    })
    _assert_result_parity(legacy, InstitutionalRadarEngine().analyze(typed_context))
