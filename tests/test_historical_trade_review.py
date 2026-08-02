from dataclasses import replace
from datetime import date, datetime

import pandas as pd
import pytest

from itos_platform.historical_trade_review import *
from itos_platform.historical_options import derive_historical_option_chain, option_coverage
from itos_platform.market_lake import DatasetManifest, HistoricalIntelligenceRecord, HistoricalOutcomeRecord

DAY=date(2026,7,10); STAMP=datetime(2026,7,10,10,20)

def record(side="BUY CE", **changes):
    values={"market_regime":{"regime":"Bullish"},"volume_structure":{"confirmed_expansion":True,"behaviour":"Accumulation"},
      "positioning_intelligence":{"state":"Long Build-up"},"compression_intelligence":{"score":80,"releasing":True},
      "manipulation_intelligence":{},"institutional_evidence":{"bias":"Bullish"},
      "trade_opportunity_ranking":{"top_ce":{"strike":25000},"top_pe":{"strike":24900}}}
    base=HistoricalIntelligenceRecord("upstox","NIFTY","NIFTY",1,DAY,STAMP,STAMP,STAMP,"engine","intelligence-v1","FULL_REPLAY",side,89,89,"A","Bullish","Long Build-up","Releasing","Low",True,(),(),(),values)
    return replace(base,**changes)

def outcome(move=30, available=True):
    r=record(); return HistoricalOutcomeRecord(r.record_id,"NIFTY",1,DAY,STAMP,"engine","outcome-v1",100,((5,100+move),(15,100+move),(30,100+move)),((5,move),(15,move),(30,move)),((5,move),(15,move),(30,move)),100+move,max(move,0),min(move,0),available)

@pytest.mark.parametrize("side,move,expected",[("BUY CE",30,"FAVOURABLE"),("BUY CE",-30,"UNFAVOURABLE"),("BUY PE",-30,"FAVOURABLE"),("BUY PE",30,"UNFAVOURABLE"),("BUY CE",5,"INCONCLUSIVE")])
def test_directional_classification(side,move,expected): assert classify_result(side,outcome(move))[0]==expected

def test_not_evaluable_never_fabricates(): assert classify_result("BUY CE",None)[0]=="NOT_EVALUABLE"
def test_wait_missed_clean_move(): assert classify_result("WAIT",outcome(30))[0]=="MISSED_OPPORTUNITY"
def test_wait_avoided_adverse_evidence(): assert classify_result("WAIT",outcome(5),adverse_or_manipulative=True)[0]=="AVOIDED"
def test_thresholds_are_configuration_driven(): assert classify_result("BUY CE",outcome(30),HistoricalTradeReviewSettings(favourable_move_threshold_points=40))[0]=="INCONCLUSIVE"

def test_checklist_has_ten_stable_groups_and_preserves_evidence():
    checks=build_trigger_checklist(record(),False)
    assert len(checks)==10 and all(c.analysis_target in NAVIGATION_REGISTRY for c in checks)
    assert any("Historical bid/ask unavailable" in c.evidence for c in checks)

def test_option_unavailable_is_not_pass(): assert build_trigger_checklist(record(),False)[-1].status=="UNAVAILABLE"
@pytest.mark.parametrize("side,state,bias,expected",[("BUY CE","Short Build-up","Bearish","FAIL"),("BUY PE","Short Build-up","Bearish","PASS")])
def test_directional_positioning_and_institutional_alignment(side,state,bias,expected):
    r=record(side); values=dict(r.values); values["institutional_evidence"]={"bias":bias}
    checks=build_trigger_checklist(replace(r,positioning_state=state,market_bias=bias,values=values),False)
    assert next(x for x in checks if x.trigger_id=="positioning").status==expected
    assert next(x for x in checks if x.trigger_id=="institutional-evidence").status==expected

def test_wait_uses_blockers_without_forcing_direction():
    r=replace(record("WAIT"),blockers=("Conflicting structure",))
    checks=build_trigger_checklist(r,False)
    assert next(x for x in checks if x.trigger_id=="market-structure").status=="PARTIAL"
    assert next(x for x in checks if x.trigger_id=="decision-validation").status=="FAIL"

def test_compression_presence_without_release_direction_is_not_pass():
    check=next(x for x in build_trigger_checklist(record(),False) if x.trigger_id=="compression")
    assert check.status=="UNAVAILABLE" or check.status=="PARTIAL"
    assert "release direction" in check.rule_applied.lower()
def test_all_pass_summary(): assert trigger_summary(tuple(TriggerCheckResult(str(i),str(i),"PASS",(),"",None,None,"market-structure") for i in range(3)))=="3/3 PASS"
def test_blocking_summary_is_deterministic():
    values=dict(record().values); values["manipulation_intelligence"]={"false_breakout":True}
    checks=build_trigger_checklist(replace(record(),values=values),False)
    assert trigger_summary(checks).startswith("FAIL — Manipulation")

def test_review_uses_frozen_record_and_factual_outcome():
    r=record(); review=build_trade_reviews((r,),(outcome(),),(DAY,))[0]
    assert review.recommendation=="BUY CE" and review.outcome_classification=="FAVOURABLE" and review.best_contract=="25000 CE"
    assert review.primary_success_reason=="Volume confirmed the move"

def test_false_breakout_reason_is_traceable():
    r=record(); values=dict(r.values); values["manipulation_intelligence"]={"false_breakout":True}
    review=build_trade_reviews((replace(r,values=values),),(outcome(-30),),())[0]
    assert review.primary_failure_reason=="False breakout"

def test_unsupported_reason_not_invented():
    r=replace(record(),values={},positioning_state=None,compression_state=None,manipulation_state=None,market_bias=None,ranking_eligibility=False,blockers=())
    review=build_trade_reviews((r,),(outcome(5),),())[0]
    assert review.primary_success_reason is None

def test_trade_table_has_no_raw_json_or_runtime_objects():
    row=trade_table_rows(build_trade_reviews((record(),),(outcome(),),(DAY,)))[0]
    assert "frozen_values" not in row and "JSON" not in row and all(not callable(v) for v in row.values())

@pytest.mark.parametrize("filters",[
 TradeReviewFilters(decisions=("BUY CE",)),TradeReviewFilters(classifications=("FAVOURABLE",)),TradeReviewFilters(minimum_confidence=80),
 TradeReviewFilters(trigger_status="PASS"),TradeReviewFilters(positioning_state="Long Build-up"),TradeReviewFilters(compression_state="Releasing"),
 TradeReviewFilters(manipulation_state="Low"),TradeReviewFilters(institutional_bias="Bullish"),TradeReviewFilters(ranking_eligibility=True),
 TradeReviewFilters(replay_completeness="FULL_REPLAY"),TradeReviewFilters(option_data_status="COMPLETE"),TradeReviewFilters(contract_search="25000"),
 TradeReviewFilters(reason_search="volume")])
def test_filters_match_without_mutating(filters):
    reviews=build_trade_reviews((record(),),(outcome(),),(DAY,)); assert len(filter_trade_reviews(reviews,filters))==1 and reviews[0].recommendation=="BUY CE"

def test_chronological_order():
    early=record(); late=replace(early,analysis_timestamp=datetime(2026,7,10,11),data_cutoff_timestamp=datetime(2026,7,10,11),latest_completed_candle_timestamp=datetime(2026,7,10,11))
    assert build_trade_reviews((late,early),(),())[0].analysis_timestamp==STAMP

def manifest(**changes): return replace(DatasetManifest("id","upstox","NIFTY","NIFTY",1,5),**changes)
@pytest.mark.parametrize("m,expected",[(manifest(available_dates=(DAY,),intelligence_dates=(DAY,),outcome_dates=(DAY,),option_dates=(DAY,)),"COMPLETE"),(manifest(available_dates=(DAY,),intelligence_dates=(DAY,),outcome_dates=(DAY,)),"PARTIAL_OPTIONS"),(manifest(),"RAW_MISSING"),(manifest(available_dates=(DAY,)),"INTELLIGENCE_MISSING"),(manifest(available_dates=(DAY,),intelligence_dates=(DAY,)),"OUTCOMES_MISSING"),(manifest(failed_dates=(DAY,)),"FAILED")])
def test_date_coverage_status(m,expected): assert build_coverage_rows(m,(DAY,))[0].status==expected

def test_no_manifest_is_raw_missing(): assert build_coverage_rows(None,(DAY,))[0].status=="RAW_MISSING"

def option_rows(): return [{"timestamp":"2026-07-10T10:00:00+05:30","expiry":"2026-07-30","strike":25000,"side":"CE","open":10,"high":12,"low":9,"close":11,"ltp":11,"volume":100,"oi":None}]
def test_derived_chain_alignment_and_missing_fields():
    frame=derive_historical_option_chain(option_rows()); assert len(frame)==1 and pd.isna(frame.iloc[0].bid) and pd.isna(frame.iloc[0].iv) and pd.isna(frame.iloc[0].greeks)
def test_option_coverage_does_not_fabricate():
    value=option_coverage(option_rows()); assert value["oi_coverage"]==0 and value["bid_ask"]=="Historical bid/ask unavailable"
def test_no_option_data_degrades(): assert option_coverage([])["derived_chain"]=="UNAVAILABLE"
def test_exports_are_structured_and_do_not_contain_secret_names():
    reviews=build_trade_reviews((record(),),(outcome(),),(DAY,)); assert b"Result Classification" in export_csv(reviews) and b"access_token" not in export_json(reviews)
