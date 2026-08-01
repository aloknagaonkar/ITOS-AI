from types import SimpleNamespace

import pandas as pd
import pytest

from engines import (
    CandleDNAEngine,
    FalseBreakoutEngine,
    InstitutionalStructureEngine,
    PatternRecognitionEngine,
    SmartCandlestickEngine,
)
from itos_platform import DecisionContext, MarketSnapshot


def _candles(count=20):
    rows = []
    for index in range(count):
        close = 100 + index * 0.4
        rows.append({
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.6,
            "close": close,
            "volume": 1000 + index * 20,
            "atr14": 1.1,
        })
    return pd.DataFrame(rows)


def _assert_parity(legacy_result, typed_result):
    assert typed_result.score == legacy_result.score
    assert typed_result.vote == legacy_result.vote
    assert typed_result.confidence == legacy_result.confidence
    assert typed_result.explanation == legacy_result.explanation
    assert typed_result.metadata == legacy_result.metadata


def _context(*, intelligence=None, recommendation=None, option_result=None,
             institutional=None, cycle_result=None, engine_results=None):
    snapshot = MarketSnapshot(
        option_result=option_result or {}, intelligence=intelligence or {}
    )
    return DecisionContext(
        market_snapshot=snapshot,
        recommendation=recommendation or {},
        institutional=institutional,
        cycle_result=cycle_result,
        engine_results=engine_results or {},
    )


@pytest.mark.parametrize("engine_class", [
    CandleDNAEngine, SmartCandlestickEngine, InstitutionalStructureEngine,
])
@pytest.mark.parametrize("intelligence", [
    {"price": {"candles": _candles(), "atr": 1.1, "vwap": 104}},
    {},
    {"price": {}},
    {"price": {"candles": "malformed"}},
])
def test_candle_and_structure_engines_have_typed_legacy_parity(engine_class, intelligence):
    legacy = {"intelligence": intelligence}
    _assert_parity(
        engine_class().analyze(legacy),
        engine_class().analyze(_context(intelligence=intelligence)),
    )


def test_pattern_recognition_has_typed_legacy_parity():
    cycle = SimpleNamespace(metadata={"phase": "Compression", "relative_volume": 1.4,
                                      "manipulation_score": 20})
    legacy = {
        "recommendation": {"side": "CE", "regime": {"relative_volume": 1.4}},
        "option_result": {"summary": {"call_oi_change": 10, "put_oi_change": 40}},
        "intelligence": {"price": {"close": 105, "vwap": 103, "ema9": 104, "ema21": 102}},
        "institutional": {"primary_strength": 15},
        "cycle_result": cycle,
    }
    typed = _context(
        intelligence=legacy["intelligence"], recommendation=legacy["recommendation"],
        option_result=legacy["option_result"], institutional=legacy["institutional"],
        cycle_result=cycle,
    )
    _assert_parity(PatternRecognitionEngine().analyze(legacy), PatternRecognitionEngine().analyze(typed))


@pytest.mark.parametrize("legacy", [{}, {"recommendation": None}, {"intelligence": {}}])
def test_pattern_recognition_malformed_inputs_degrade_identically(legacy):
    _assert_parity(
        PatternRecognitionEngine().analyze(legacy),
        PatternRecognitionEngine().analyze(_context()),
    )



@pytest.mark.parametrize("legacy", [{}, {"structure_result": None}, {"candle_dna_result": None}])
def test_false_breakout_missing_structure_degrades_identically(legacy):
    _assert_parity(
        FalseBreakoutEngine().analyze(legacy),
        FalseBreakoutEngine().analyze(_context()),
    )


def test_false_breakout_has_typed_legacy_parity_and_preserves_blocking():
    structure = SimpleNamespace(metadata={"primary": {"status": "CONFIRMED", "direction": "CE"}})
    candle = SimpleNamespace(metadata={"relative_volume": 0.8, "body_pct": 20})
    footprint = SimpleNamespace(metadata={"direction": "PE"})
    cycle = SimpleNamespace(metadata={"manipulation_score": 80})
    legacy = {"structure_result": structure, "candle_dna_result": candle,
              "footprint_result": footprint, "cycle_result": cycle}
    typed = _context(cycle_result=cycle, engine_results={
        "institutional_structure": structure, "candle_dna": candle,
        "institutional_footprint": footprint,
    })
    legacy_result = FalseBreakoutEngine().analyze(legacy)
    typed_result = FalseBreakoutEngine().analyze(typed)
    _assert_parity(legacy_result, typed_result)
    assert typed_result.metadata["blocked"] is True
    assert typed_result.vote == "BLOCK"
