from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import pytest
from itos_platform.market_lake import HistoricalIntelligenceRecord
from itos_platform.historical_intelligence_index import (FEATURE_REGISTRY, HistoricalIndexQuery, HistoricalIndexSettings, HistoricalIntelligenceIndexService, HistoricalStatisticsCache, SQLiteHistoricalIntelligenceIndex, build_fingerprint, build_relationships, indexed_record, make_trade_id)
STAMP=datetime(2026,7,10,10,20,tzinfo=timezone.utc)
def raw(**changes):
 base=dict(provider="archive",instrument_key="NIFTY",underlying="NIFTY",interval_minutes=1,trading_date=STAMP.date(),analysis_timestamp=STAMP,data_cutoff_timestamp=STAMP,latest_completed_candle_timestamp=STAMP,engine_version="engine-1",schema_version="intelligence-v1",replay_completeness="CANDLE_ONLY_REPLAY",recommendation="BUY CE",recommendation_confidence=90,decision_confidence=95,market_bias="BULLISH",positioning_state="long buildup",compression_state="HIGH COMPRESSION",manipulation_state="NONE",ranking_eligibility=True,values={"market_structure":"bullish","validation_state":"eligible","compression_score":120,"volume_strength":50,"trigger_pass_ratio":.75});base.update(changes);return HistoricalIntelligenceRecord(**base)
def cfg(p,**changes):return replace(HistoricalIndexSettings(historical_index_path=p/"index.sqlite",index_query_maximum_limit=100),**changes)
def test_trade_id_stability_sensitivity_and_readability():
 r=raw(); identifier=make_trade_id(r);assert identifier==make_trade_id(r)==r.trade_id;assert identifier.startswith("HTR-NIFTY-20260710-102000-1M-")
 for changed in (replace(r,analysis_timestamp=STAMP.replace(minute=21)),replace(r,instrument_key="OTHER"),replace(r,interval_minutes=5),replace(r,engine_version="v2")):assert make_trade_id(changed)!=identifier
 assert "archive" not in identifier
@pytest.mark.parametrize(("rec","token","direction"),[("BUY CE","REC=BUY_CE","BULLISH"),("BUY PE","REC=BUY_PE","BEARISH"),("WAIT","REC=WAIT","NEUTRAL")])
def test_fingerprint_recommendations(rec,token,direction):
 fp=build_fingerprint(raw(recommendation=rec));assert token in fp.semantic_tokens and fp.direction==direction
def test_fingerprint_semantic_numeric_no_outcome_and_immutable():
 fp=build_fingerprint(raw(values={**raw().values,"outcome_classification":"SUCCESS","mfe":999}));assert fp==build_fingerprint(raw(values={**raw().values,"outcome_classification":"SUCCESS","mfe":999}))
 assert "POS=LONG_BUILDUP" in fp.semantic_tokens and "COMP=HIGH_COMPRESSION" in fp.semantic_tokens and "CONF=90_100" in fp.semantic_tokens and "VALID=ELIGIBLE" in fp.semantic_tokens
 assert not any("OUTCOME" in x or "MFE" in x for x in fp.semantic_tokens);features=dict(fp.numeric_features);assert tuple(features)==tuple(x.name for x in FEATURE_REGISTRY)
 assert features["decision_confidence"]==.95 and features["compression_score"]==1 and features["volume_strength"]==.5 and features["iv_percentile"] is None
 with pytest.raises(FrozenInstanceError):fp.trade_id="x"
def test_invalid_and_missing_numeric_degrade_safely():
 fp=build_fingerprint(raw(values={"compression_score":"bad"}));assert dict(fp.numeric_features)["compression_score"] is None;assert "FEATURE_VALUE_INVALID" in fp.quality_flags and "FINGERPRINT_INCOMPLETE" in fp.quality_flags
def test_sqlite_queries_versions_security_and_pagination(tmp_path):
 idx=SQLiteHistoricalIntelligenceIndex(cfg(tmp_path));a=indexed_record(raw(),idx.settings);b=indexed_record(raw(instrument_key="OTHER",analysis_timestamp=STAMP.replace(minute=22),recommendation="BUY PE"),idx.settings);idx.bulk_upsert((a,b));idx.upsert(a)
 assert idx.get_by_trade_id(a.trade_id)==a and idx.get_by_trade_id("missing") is None;assert idx.query(HistoricalIndexQuery(instrument_key="OTHER"))==(b,);assert idx.query(HistoricalIndexQuery(recommendation="BUY CE",minimum_confidence=90,semantic_tokens_all=("REC=BUY_CE",)))==(a,)
 assert len(idx.query(HistoricalIndexQuery(semantic_tokens_any=("REC=BUY_CE","REC=BUY_PE"),limit=1,offset=1)))==1;assert idx.query(HistoricalIndexQuery(instrument_key="x' OR 1=1--"))==();assert idx.list_versions()==("fp-v1",)
 with pytest.raises(ValueError):idx.query(HistoricalIndexQuery(order_by="trade_id; DROP TABLE x"))
 with pytest.raises(ValueError):idx.query(HistoricalIndexQuery(limit=101))
 idx.delete_version("fp-v1");assert idx.query()==()
def test_schema_mismatch_preserved(tmp_path):
 SQLiteHistoricalIntelligenceIndex(cfg(tmp_path))
 with pytest.raises(RuntimeError,match="INDEX_SCHEMA_MISMATCH"):SQLiteHistoricalIntelligenceIndex(cfg(tmp_path,historical_index_schema_version="2"))
def test_incremental_build_duplicate_checkpoint_and_outcome_separation(tmp_path):
 idx=SQLiteHistoricalIntelligenceIndex(cfg(tmp_path,index_batch_size=1,index_checkpoint_interval=1));service=HistoricalIntelligenceIndexService(idx,idx.settings,tmp_path/"cp.json");result=service.build((raw(),raw()));assert (result.completed,result.duplicate_trade_ids)==(1,1) and (tmp_path/"cp.json").exists();assert service.build((raw(),)).skipped==1
 item=idx.query()[0];before=item.numeric_features;service.refresh_outcome_metadata(item.trade_id,item.fingerprint_version,outcome_classification="GOOD");assert idx.get_by_trade_id(item.trade_id).numeric_features==before and idx.get_by_trade_id(item.trade_id).outcome_classification=="GOOD"
def test_statistics_cache_invalidates(tmp_path):
 idx=SQLiteHistoricalIntelligenceIndex(cfg(tmp_path));cache=HistoricalStatisticsCache(idx);idx.upsert(indexed_record(raw(),idx.settings));result=cache.compute();assert result["recommendation_counts"]=={"BUY CE":1} and result["confidence_median"]==95 and cache.get()==result
 idx.upsert(indexed_record(raw(instrument_key="OTHER",analysis_timestamp=STAMP.replace(minute=22)),idx.settings));assert cache.get() is None
def test_relationship_graph_deterministic_opposite_and_no_self(tmp_path):
 settings=cfg(tmp_path,relationship_minimum_overlap=1);a=indexed_record(raw(),settings,outcome_classification="GOOD");b=indexed_record(raw(instrument_key="B",analysis_timestamp=STAMP.replace(minute=21)),settings,outcome_classification="BAD");c=indexed_record(raw(instrument_key="C",analysis_timestamp=STAMP.replace(minute=22),recommendation="BUY PE"),settings,outcome_classification="GOOD");graph=build_relationships((c,b,a),settings)
 assert graph==build_relationships((a,b,c),settings);assert all(x.source_trade_id!=x.target_trade_id and 0<=x.preliminary_score<=1 for x in graph);assert any(x.relationship_type=="SAME_SETUP_DIFFERENT_OUTCOME" and x.preliminary_score==1 for x in graph);assert any(x.relationship_type=="OPPOSITE_DIRECTION" for x in graph)
