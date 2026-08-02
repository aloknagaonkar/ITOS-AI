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

def nested_raw(**changes):
 values={
  "market_structure":{"state":"bullish"},"market_regime":{"regime":"trending"},"market_cycle":{"cycle":"markup"},
  "market_location":{"location":"bottom","score":65},"volume_structure":{"state":"expanding","volume_strength":80},
  "positioning_intelligence":{"state":"long buildup","confidence":72,"options":{"state":"put writing"}},
  "compression_intelligence":{"state":"high compression","compression_score":88,"energy_stored":70,"expansion_readiness":60,"release_state":"releasing"},
  "manipulation_intelligence":{"state":"none","confidence":25,"trap_state":"none"},
  "institutional_evidence":{"bias":"bullish","quality":85},"decision_confidence":{"score":91},
  "decision_confidence_validation":{"state":"eligible","score":87},"trade_opportunity_ranking":{"state":"eligible","score":86},
  "trigger_review":{"summary":"passed","pass_ratio":.8},"outcome":{"classification":"FAIL","mfe":999},
 }
 base=raw(decision_confidence=None,recommendation_confidence=None,positioning_state=None,compression_state=None,manipulation_state=None,values=values);return replace(base,**changes)

def test_nested_and_legacy_alias_extraction_without_outcome_leakage():
 fp=build_fingerprint(nested_raw());tokens=set(fp.semantic_tokens);features=dict(fp.numeric_features)
 assert {"MS=BULLISH","REGIME=TRENDING","CYCLE=MARKUP","LOC=BOTTOM","PV=EXPANDING","POS=LONG_BUILDUP","OPTPOS=PUT_WRITING","COMP=HIGH_COMPRESSION","INST=BULLISH","VALID=ELIGIBLE"}<=tokens
 assert features["decision_confidence"]==.91 and features["compression_score"]==.88 and features["volume_strength"]==.8 and features["ranking_score"]==.86
 assert not any("OUTCOME" in token or "FAIL" in token or "999" in token for token in fp.semantic_tokens) and all(name not in {"mfe","outcome"} for name,_ in fp.numeric_features)
 legacy=build_fingerprint(raw(values={"market_structure":"bearish","compression_score":50}));assert "MS=BEARISH" in legacy.semantic_tokens and dict(legacy.numeric_features)["compression_score"]==.5
 missing=build_fingerprint(raw(values={}));assert "MS=UNKNOWN" in missing.semantic_tokens and dict(missing.numeric_features)["volume_strength"] is None

def test_status_missing_outdated_and_invalid_json(tmp_path):
 old=cfg(tmp_path,fingerprint_version="fp-old");idx=SQLiteHistoricalIntelligenceIndex(old);idx.upsert(indexed_record(raw(),old));idx.settings=replace(old,fingerprint_version="fp-new")
 missing=raw(instrument_key="MISSING",analysis_timestamp=STAMP.replace(minute=23));status=idx.get_status((raw(),missing));assert status.total_market_lake_records==2 and status.total_indexed_records==1 and status.outdated_fingerprint_records==1 and status.missing_index_records==1 and "FINGERPRINT_VERSION_OUTDATED" in status.quality_flags
 with idx._connect() as db:db.execute("UPDATE historical_intelligence_index SET numeric_features='not-json'")
 validation=idx.validate_index((raw(),));assert validation["invalid_records"]==1 and "INDEX_RECORD_INVALID" in validation["quality_flags"]

def test_statistics_process_every_page_and_reports_completeness(tmp_path):
 settings=cfg(tmp_path,index_query_maximum_limit=2);idx=SQLiteHistoricalIntelligenceIndex(settings)
 idx.bulk_upsert(tuple(indexed_record(raw(instrument_key=f"I{i}",analysis_timestamp=STAMP.replace(minute=20+i)),settings) for i in range(5)))
 result=HistoricalStatisticsCache(idx).compute();assert result["matching_record_count"]==result["processed_record_count"]==5 and result["complete"] is True and result["quality_flags"]==[] and result["recommendation_counts"]=={"BUY CE":5}

def test_symmetric_neighbors_and_limit_per_trade(tmp_path):
 from itos_platform.historical_intelligence_index import get_neighbors
 settings=cfg(tmp_path,relationship_minimum_overlap=1,relationship_maximum_neighbors=1);records=tuple(indexed_record(raw(instrument_key=f"N{i}",analysis_timestamp=STAMP.replace(minute=20+i)),settings) for i in range(3));graph=build_relationships(records,settings)
 assert all(len(get_neighbors(graph,r.trade_id))==1 for r in records);edge=graph[0];assert any(x.source_trade_id==edge.target_trade_id and x.target_trade_id==edge.source_trade_id and x.preliminary_score==edge.preliminary_score for x in graph)

def test_checkpoint_resume_versions_and_full_rebuild(tmp_path):
 settings=cfg(tmp_path,index_batch_size=1,index_checkpoint_interval=1);idx=SQLiteHistoricalIntelligenceIndex(settings);records=tuple(raw(instrument_key=f"R{i}",analysis_timestamp=STAMP.replace(minute=20+i)) for i in range(3));service=HistoricalIntelligenceIndexService(idx,settings,tmp_path/"cp.json")
 assert service.build(records[:2]).completed==2;assert service.build(records,resume=True).completed==1;assert len(idx.query())==3
 newer=replace(settings,fingerprint_version="fp-v2");new_service=HistoricalIntelligenceIndexService(idx,newer,tmp_path/"cp2.json");assert new_service.build(records).skipped==3;assert new_service.build(records,rebuild_outdated=True).completed==3;assert idx.list_versions()==("fp-v1","fp-v2")
 assert new_service.build(records,full_rebuild=True).completed==3 and len(idx.query(HistoricalIndexQuery(fingerprint_version="fp-v2")))==3

def test_collision_detection_and_transaction_rollback(tmp_path):
 settings=cfg(tmp_path);idx=SQLiteHistoricalIntelligenceIndex(settings);a=indexed_record(raw(),settings);other=raw(instrument_key="OTHER");assert make_trade_id(raw(),settings,digest_strategy=lambda _:"a"*64)==make_trade_id(other,settings,digest_strategy=lambda _:"a"*64)
 b=replace(indexed_record(other,settings),trade_id=a.trade_id)
 with pytest.raises(ValueError,match="TRADE_ID_COLLISION"):idx.bulk_upsert((a,b))
 assert idx.query()==()

def test_auto_update_enabled_disabled_enrichment_and_failure_isolation(tmp_path):
 from itos_platform.historical_intelligence_index import HistoricalIndexAutoUpdater
 settings=cfg(tmp_path);idx=SQLiteHistoricalIntelligenceIndex(settings);service=HistoricalIntelligenceIndexService(idx,settings);off=HistoricalIndexAutoUpdater(service);assert off.on_live_record(raw()) is False and idx.query()==()
 on=HistoricalIndexAutoUpdater(service,live_enabled=True,enrichment_enabled=True);assert on.on_live_record(raw()) and len(idx.query())==1;enriched=raw(instrument_key="E",analysis_timestamp=STAMP.replace(minute=22));assert on.on_enriched_record(enriched) and len(idx.query())==2
 class Broken:
  def build(self,*a,**k):raise RuntimeError("boom")
 broken=HistoricalIndexAutoUpdater(Broken(),live_enabled=True);assert broken.on_live_record(raw()) is False and broken.diagnostics
