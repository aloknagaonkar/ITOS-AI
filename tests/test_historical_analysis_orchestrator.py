from datetime import date
from types import SimpleNamespace as Result
import json
import pytest
from itos_platform.historical_analysis_orchestrator import (
 HistoricalAnalysisOrchestrator,HistoricalAnalysisRunRequest,HistoricalAnalysisSettings,
 JsonRunCheckpointStore,PipelineStage)

D1=date(2026,7,1); D2=date(2026,7,2)
def request(**changes):
 values=dict(underlying="NIFTY",instrument_key="NIFTY",start_date=D1,end_date=D2)
 values.update(changes); return HistoricalAnalysisRunRequest(**values)
def raw(day,*,existing=frozenset(),failed=frozenset(),no_data=frozenset()):
 return Result(requested_dates=(day,),completed_dates=() if day in existing|failed|no_data else (day,),
  skipped_dates=(day,) if day in existing else (),no_data_dates=(day,) if day in no_data else (),
  failed_dates=(day,) if day in failed else (),downloaded_row_count=10,stored_row_count=9)
def intelligence(day,failed=frozenset()):
 return Result(completed_dates=() if day in failed else (day,),skipped_dates=(),failed_dates=(day,) if day in failed else (),completed=3)
def pipeline(tmp_path=None,**overrides):
 calls=[]
 def sync(req): calls.append(("raw",req.start_date)); return raw(req.start_date)
 def options(req): calls.append(("options",req.start_date)); return Result(expiries_discovered=1,contracts_discovered=4,contracts_stored=4,failed_contracts=0,status="FULL")
 def intel(req,cadence_minutes=5): calls.append(("intel",req.start_date,cadence_minutes)); return intelligence(req.start_date)
 def outcomes(req): calls.append(("outcome",req.start_date)); return (Result(status="FAVOURABLE"),)
 def index(req): calls.append(("index",req.start_date)); return Result(completed=1,skipped=0,failed=0)
 args=dict(sync_underlying=sync,download_options=options,build_intelligence=intel,build_outcomes=outcomes,
  build_index=index,prepare_analytics=lambda req:{"ready":True},checkpoint_store=JsonRunCheckpointStore(tmp_path) if tmp_path else None)
 args.update(overrides); return HistoricalAnalysisOrchestrator(**args),calls

def test_validation():
 settings=HistoricalAnalysisSettings(maximum_date_range_days=5); supported={"NIFTY":"NIFTY"}
 with pytest.raises(ValueError): request(start_date=D2,end_date=D1).validate(settings,supported)
 with pytest.raises(ValueError): request(instrument_key="BAD").validate(settings,supported)

def test_real_results_map_existing_download_failure_and_true_counts(tmp_path):
 def sync(req): return raw(req.start_date,existing={D1},failed={D2})
 orch,_=pipeline(tmp_path,sync_underlying=sync); result=orch.run(request(),run_id="mapping")
 rows={r.trading_date:r for r in result.progress.date_statuses}
 assert rows[D1].underlying=="Existing" and rows[D1].final=="Ready"
 assert rows[D2].underlying=="Failed" and rows[D2].final=="Retry Required"
 assert result.progress.underlying_complete==1
 assert result.progress.downloaded_rows==20 and result.progress.stored_rows==18
 assert result.progress.overall_percent==100 and result.progress.stage_percent==100

def test_provider_no_data_blocks_dependent_work():
 def sync(req): return raw(req.start_date,no_data={D2})
 orch,calls=pipeline(sync_underlying=sync); result=orch.run(request())
 assert result.progress.date_statuses[1].underlying=="Provider No Data"
 assert not any(call[0]=="intel" and call[1]==D2 for call in calls)

def test_option_partial_is_isolated_to_one_date():
 def options(req): return Result(expiries_discovered=1,contracts_discovered=4,contracts_stored=3,
  failed_contracts=1 if req.start_date==D1 else 0,status="PARTIAL")
 result=pipeline(download_options=options)[0].run(request())
 assert [r.options for r in result.progress.date_statuses]==["Partial Options","Available"]
 assert result.progress.option_contracts_failed==1

def test_intelligence_failure_outcome_pending_and_index_failure_are_isolated():
 def intel(req,cadence_minutes=5): return intelligence(req.start_date,failed={D2})
 def outcomes(req): return ()
 def index(req): return Result(completed=0,skipped=0,failed=1 if req.start_date==D1 else 0)
 result=pipeline(build_intelligence=intel,build_outcomes=outcomes,build_index=index)[0].run(request())
 rows=result.progress.date_statuses
 assert rows[0].outcomes=="Outcomes Pending" and rows[0].index=="Index Failed"
 assert rows[0].final=="Ready — Similarity unavailable"
 assert rows[1].intelligence=="Intelligence Failed" and rows[1].final=="Retry Required"

def test_non_default_cadence_propagates():
 orch,calls=pipeline(); orch.run(request(analysis_cadence_minutes=15))
 assert [call[2] for call in calls if call[0]=="intel"]==[15,15]

def test_checkpoint_load_schema_and_no_token(tmp_path):
 orch,_=pipeline(tmp_path); result=orch.run(request(),run_id="load")
 saved_request,progress=JsonRunCheckpointStore(tmp_path).load("load")
 assert saved_request==request() and progress.run_id==result.run_id
 assert "token" not in (tmp_path/"load.json").read_text().lower()
 payload=json.loads((tmp_path/"load.json").read_text()); payload["schema_version"]=999
 (tmp_path/"bad.json").write_text(json.dumps(payload))
 with pytest.raises(ValueError): JsonRunCheckpointStore(tmp_path).load("bad")

def test_resume_new_instance_retries_failed_date_only(tmp_path):
 first_calls=[]
 def first(req): first_calls.append(req.start_date); return raw(req.start_date,failed={D2})
 first_orch,_=pipeline(tmp_path,sync_underlying=first); first_orch.run(request(),run_id="resume")
 second_orch,calls=pipeline(tmp_path); result=second_orch.retry_failed_dates(request(),"resume")
 assert not any(c[0]=="raw" and c[1]==D1 for c in calls)
 assert any(c[0]=="raw" and c[1]==D2 for c in calls)
 assert result.progress.date_statuses[1].final=="Ready"

def test_cancel_after_atomic_date_and_resume(tmp_path):
 checks=iter((False,True)); orch,calls=pipeline(tmp_path,should_cancel=lambda:next(checks,True))
 result=orch.run(request(),run_id="cancel")
 assert result.status=="CANCELLED" and [c for c in calls if c[0]=="raw"]==[("raw",D1),("raw",D2)]
 resumed,calls2=pipeline(tmp_path); resumed.retry_failed_dates(request(),"cancel")
 assert not any(c[0]=="raw" for c in calls2)

def test_index_only_retry_does_not_repeat_source_stages(tmp_path):
 def index(req): return Result(completed=0,skipped=0,failed=1)
 pipeline(tmp_path,build_index=index)[0].run(request(),run_id="index")
 resumed,calls=pipeline(tmp_path); result=resumed.retry_index_only(request(),"index")
 assert {c[0] for c in calls}=={"index"}
 assert all(r.index=="Indexed" for r in result.progress.date_statuses)

@pytest.mark.parametrize(("index_result","index_status","final_status"),(
 (Result(completed=1,skipped=0,failed=0),"Indexed","Ready"),
 (Result(completed=0,skipped=1,failed=0),"Indexed","Ready"),
 (Result(completed=0,skipped=0,failed=1),"Index Failed","Ready — Similarity unavailable"),
 (Result(completed=0,skipped=0,failed=0),"Index Pending","Partial"),
))
def test_index_result_mapping_and_readiness(index_result,index_status,final_status):
 def index(_request): return index_result
 result=pipeline(build_index=index)[0].run(request(start_date=D1,end_date=D1))
 row=result.progress.date_statuses[0]
 assert row.index==index_status
 assert row.final==final_status
