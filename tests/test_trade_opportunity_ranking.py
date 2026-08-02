"""Behavioural contracts for Sprint 18's informational ranking engine."""

from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from itos_platform.decision_context import DecisionContext, MarketSnapshot
from itos_platform.trade_opportunity_ranking import (
    TradeOpportunityRankingEngine, TradeOpportunityRankingSettings,
)
from dashboard_application_service import DashboardApplicationResult


def _chain(**overrides):
    expiry = (date.today() + timedelta(days=7)).isoformat()
    base = {
        "strike": [98, 99, 100, 101, 102, 103], "expiry": [expiry] * 6,
        "call_ltp": [4, 3, 2, 1.5, 1, .5], "put_ltp": [.5, 1, 2, 3, 4, 5],
        "call_bid": [3.9, 2.9, 1.95, 1.45, .95, .45], "call_ask": [4.1, 3.1, 2.05, 1.55, 1.05, .55],
        "put_bid": [.45, .95, 1.95, 2.9, 3.9, 4.9], "put_ask": [.55, 1.05, 2.05, 3.1, 4.1, 5.1],
        "call_oi": [1000] * 6, "put_oi": [1000] * 6, "call_oi_change": [50] * 6, "put_oi_change": [50] * 6,
        "call_volume": [500] * 6, "put_volume": [500] * 6, "call_iv": [20] * 6, "put_iv": [20] * 6,
        "call_delta": [.7, .6, .5, .4, .3, .2], "put_delta": [-.2, -.3, -.5, -.6, -.7, -.8],
        "call_gamma": [.02] * 6, "put_gamma": [.02] * 6, "call_theta": [-2] * 6, "put_theta": [-2] * 6,
        "call_vega": [1] * 6, "put_vega": [1] * 6,
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _context(chain=None, *, ready=True, eligible=True, bias="BULLISH", score=80,
             stability="STABLE", spot=100, manipulation=None):
    option = {} if chain is None else {"chain": chain, "summary": {"spot": spot}}
    return DecisionContext(
        market_snapshot=MarketSnapshot(option_result=option, intelligence={}, expiry=(date.today() + timedelta(days=7)).isoformat()),
        recommendation={"side": "WAIT", "status": "WAIT"},
        institutional_evidence=SimpleNamespace(bias=bias),
        positioning_intelligence=SimpleNamespace(dominant_state="LONG_BUILDUP"),
        manipulation_intelligence=manipulation or SimpleNamespace(bull_trap_risk=0, bear_trap_risk=0),
        decision_confidence=SimpleNamespace(ranking_ready=ready, score=score),
        decision_confidence_validation=SimpleNamespace(
            ranking_eligible=eligible, ranking_eligibility_state="ELIGIBLE", stability_state=stability
        ),
    )


def test_gate_passes_and_both_top_five_lists_are_ranked_without_changing_recommendation():
    context = _context(_chain())
    before = dict(context.recommendation)
    result = TradeOpportunityRankingEngine().analyze(context)
    assert result.ranking_state == "RANKED"
    assert result.ranking_eligible is True
    assert len(result.top_ce) == len(result.top_pe) == 5
    assert context.recommendation == before == {"side": "WAIT", "status": "WAIT"}
    assert all(0 <= value <= 100 for item in result.top_ce + result.top_pe for value in (
        item.opportunity_score, item.liquidity_score, item.spread_quality_score,
        item.oi_volume_score, item.greeks_score, item.iv_score, item.moneyness_score,
        item.direction_compatibility_score, item.expiry_score, item.risk_score,
    ))


@pytest.mark.parametrize(("ready", "eligible", "reason"), [
    (False, True, "not ready"), (True, False, "not eligible"),
])
def test_ranking_gate_failure_returns_no_partial_ranking(ready, eligible, reason):
    result = TradeOpportunityRankingEngine().analyze(_context(_chain(), ready=ready, eligible=eligible))
    assert result.ranking_state == "NOT_ELIGIBLE"
    assert result.top_ce == result.top_pe == ()
    assert result.best_ce is result.best_pe is result.best_overall is None
    assert reason in result.eligibility_reason.lower()


@pytest.mark.parametrize(("chain", "spot", "flag"), [
    (None, 100, "OPTION_CHAIN_UNAVAILABLE"),
    (pd.DataFrame(), 100, "OPTION_CHAIN_EMPTY"),
    (_chain(), None, "SPOT_UNAVAILABLE"),
])
def test_missing_market_inputs_degrade_safely(chain, spot, flag):
    result = TradeOpportunityRankingEngine().analyze(_context(chain, spot=spot))
    assert result.ranking_eligible is False
    assert flag in result.quality_flags


def test_bullish_and_bearish_bias_prefer_the_matching_side():
    bullish = TradeOpportunityRankingEngine().analyze(_context(_chain(), bias="BULLISH"))
    bearish = TradeOpportunityRankingEngine().analyze(_context(_chain(), bias="BEARISH"))
    assert bullish.preferred_direction == "CE" and bullish.best_overall.option_type == "CE"
    assert bearish.preferred_direction == "PE" and bearish.best_overall.option_type == "PE"
    assert bullish.top_ce[0].direction_compatibility_score > bullish.top_pe[0].direction_compatibility_score


@pytest.mark.parametrize(("bias", "direction"), [("NEUTRAL", "NEUTRAL"), ("CONFLICTED", "CONFLICTED")])
def test_neutral_and_conflicted_bias_do_not_force_a_side(bias, direction):
    result = TradeOpportunityRankingEngine().analyze(_context(_chain(), bias=bias))
    assert result.preferred_direction == direction
    if bias == "CONFLICTED": assert result.best_overall is None


def test_tight_spread_and_high_liquidity_improve_contract_score():
    chain = _chain()
    chain.loc[0, ["call_bid", "call_ask", "call_oi", "call_volume"]] = [3.99, 4.01, 10000, 5000]
    chain.loc[1, ["call_bid", "call_ask", "call_oi", "call_volume"]] = [2.6, 3.4, 110, 11]
    result = TradeOpportunityRankingEngine().analyze(_context(chain))
    by_strike = {item.strike: item for item in result.top_ce}
    assert by_strike[98].spread_quality_score > by_strike[99].spread_quality_score
    assert by_strike[98].liquidity_score > by_strike[99].liquidity_score


def test_critical_spread_low_oi_volume_and_deep_otm_are_rejected_with_reasons():
    settings = TradeOpportunityRankingSettings(maximum_distance_percent=20, deep_otm_percent=8)
    chain = _chain()
    chain.loc[0, ["call_bid", "call_ask"]] = [.1, 4]
    chain.loc[1, "call_oi"] = 1
    chain.loc[2, "call_volume"] = 1
    chain.loc[5, "strike"] = 110
    result = TradeOpportunityRankingEngine(settings).analyze(_context(chain))
    reasons = {reason for item in result.rejected for reason in item.rejection_reasons}
    assert {"Spread is critically wide", "OI below minimum", "Volume below minimum", "Deep OTM beyond allowed distance"} <= reasons


def test_missing_optional_metrics_are_not_fabricated_and_degrade_with_flags():
    chain = _chain().drop(columns=["call_iv", "call_delta", "call_gamma", "call_theta", "call_vega"])
    result = TradeOpportunityRankingEngine().analyze(_context(chain))
    candidate = result.top_ce[0]
    assert candidate.iv is candidate.delta is candidate.gamma is candidate.theta is candidate.vega is None
    assert {"IV_UNAVAILABLE", "GREEKS_UNAVAILABLE"} <= set(candidate.quality_flags)


def test_delta_theta_gamma_iv_and_low_dte_penalties_are_explained():
    expiry = date.today().isoformat()
    chain = _chain(expiry=[expiry] * 6)
    chain.loc[0, ["call_delta", "call_gamma", "call_theta", "call_iv"]] = [.02, .2, -50, 80]
    result = TradeOpportunityRankingEngine().analyze(_context(chain))
    candidate = next(item for item in result.top_ce if item.strike == 98)
    warning_text = " ".join(candidate.warnings)
    assert "Delta" in warning_text and "Theta" in warning_text and "gamma" in warning_text and "IV" in warning_text
    assert candidate.expiry_score < 60


def test_side_specific_manipulation_rejects_only_affected_side():
    manipulation = SimpleNamespace(bull_trap_risk=90, bear_trap_risk=5)
    result = TradeOpportunityRankingEngine().analyze(_context(_chain(), manipulation=manipulation))
    assert not result.top_ce and result.top_pe
    assert any("Severe manipulation risk on CE side" in item.rejection_reasons for item in result.rejected)


def test_confidence_weighting_and_unstable_history_grade_cap_are_applied():
    high = TradeOpportunityRankingEngine().analyze(_context(_chain(), score=95))
    low = TradeOpportunityRankingEngine().analyze(_context(_chain(), score=60))
    unstable = TradeOpportunityRankingEngine().analyze(_context(_chain(), score=100, stability="UNSTABLE"))
    assert high.top_ce[0].opportunity_score > low.top_ce[0].opportunity_score
    assert unstable.top_ce[0].grade not in {"A", "A_PLUS"}


def test_duplicate_and_malformed_rows_are_deterministic_and_rejections_retained():
    rows = _chain().to_dict("records")
    rows += [dict(rows[0]), {"unexpected": "row"}]
    first = TradeOpportunityRankingEngine().analyze(_context(rows))
    second = TradeOpportunityRankingEngine().analyze(_context(rows))
    assert [(x.strike, x.opportunity_score) for x in first.top_ce] == [(x.strike, x.opportunity_score) for x in second.top_ce]
    assert len({(x.option_type, x.strike, str(x.expiry)) for x in first.top_ce + first.top_pe}) == len(first.top_ce + first.top_pe)
    assert "OPTION_ROWS_INVALID" in first.quality_flags
    assert any("Malformed option row" in item.rejection_reasons for item in first.rejected)


def test_row_per_contract_aliases_and_candidate_explanation_are_supported():
    expiry = (date.today() + timedelta(days=7)).isoformat()
    rows = [{"strike_price": 100, "type": "CALL", "expiry_date": expiry,
             "last_price": 2, "bid_price": 1.95, "ask_price": 2.05,
             "open_interest": 1000, "traded_volume": 500,
             "implied_volatility": 20, "delta": .5, "gamma": .02, "theta": -2, "vega": 1}]
    result = TradeOpportunityRankingEngine().analyze(_context(rows))
    assert result.best_ce.option_type == "CE"
    assert "ranked because" in result.best_ce.explanation
    assert "ranks #1" in result.best_ce.explanation


def test_exact_ranking_instance_can_be_shared_by_context_and_mapping():
    ranking = TradeOpportunityRankingEngine().analyze(_context(_chain()))
    context = _context(_chain())
    shared = DecisionContext(**{**context.__dict__, "trade_opportunity_ranking": ranking})
    assert shared.trade_opportunity_ranking is ranking
    assert shared.engine_results["trade_opportunity_ranking"] is ranking
    dashboard = DashboardApplicationResult({"trade_opportunity_ranking": ranking})
    assert dashboard.trade_opportunity_ranking is ranking
