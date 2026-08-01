from engines.ai_orchestrator import AIOrchestrator
from engines.institutional_confidence import InstitutionalConfidenceEngine
from engines.strike_ranker import StrikeRanker


def sample_market():
    return {
        "spot": 24860,
        "vwap": 24820,
        "pcr": 1.18,
        "pcr_change": 0.05,
        "ce_change_oi": 100000,
        "pe_change_oi": 260000,
        "call_volume": 120000,
        "put_volume": 180000,
        "trend": "bullish",
        "future_price": 24892,
        "max_pain": 24800,
        "delta": 0.56,
        "gamma": 0.03,
        "strikes": [
            {"strike": 24850, "option_type": "CE", "ltp": 182, "bid": 181.5, "ask": 182.5, "oi": 450000, "change_oi": 85000, "volume": 190000, "delta": 0.55, "iv": 14},
            {"strike": 24900, "option_type": "CE", "ltp": 156, "bid": 154, "ask": 158, "oi": 310000, "change_oi": 62000, "volume": 145000, "delta": 0.48, "iv": 15},
        ],
    }


def test_confidence_is_directional():
    result = InstitutionalConfidenceEngine().analyze(sample_market())
    assert result.vote == "CE"
    assert result.confidence >= 60


def test_ranker_returns_best_first():
    ranked = StrikeRanker().rank(sample_market()["strikes"], "CE", 24860)
    assert ranked[0]["score"] >= ranked[1]["score"]


def test_orchestrator_returns_recommendation():
    result = AIOrchestrator().evaluate(sample_market())
    assert result["decision"] in {"BUY CE", "WAIT"}
    assert result["engine_errors"] == []


if __name__ == "__main__":
    test_confidence_is_directional()
    test_ranker_returns_best_first()
    test_orchestrator_returns_recommendation()
    print("ITOS v9.2.1 smoke tests passed")
