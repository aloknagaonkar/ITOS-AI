"""Reliable, resumable one-click Historical Analysis orchestration."""
from __future__ import annotations
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4
from .market_lake import HistoricalRangeRequest, MarketLakeSettings

class PipelineStage(str, Enum):
    PLAN="PLAN"; DOWNLOAD_UNDERLYING="DOWNLOAD_UNDERLYING"; DOWNLOAD_OPTIONS="DOWNLOAD_OPTIONS"
    BUILD_INTELLIGENCE="BUILD_INTELLIGENCE"; BUILD_OUTCOMES="BUILD_OUTCOMES"; BUILD_INDEX="BUILD_INDEX"
    PREPARE_ANALYTICS="PREPARE_ANALYTICS"; COMPLETE="COMPLETE"
STAGE_ORDER={stage:index for index,stage in enumerate(PipelineStage)}

@dataclass(frozen=True)
class HistoricalAnalysisSettings:
    simple_ui_enabled: bool=True; default_underlying: str="NIFTY"; default_interval_minutes: int=1
    default_cadence_minutes: int=5; include_options_default: bool=True; maximum_date_range_days: int=366
    auto_build_intelligence: bool=True; auto_build_outcomes: bool=True; auto_build_index: bool=True
    auto_prepare_analytics: bool=True; checkpoint_enabled: bool=True; resume_enabled: bool=True
    cancel_after_current_date_enabled: bool=True; retry_failed_dates_enabled: bool=True
    missed_opportunity_summary_enabled: bool=True; normal_ui_json_disabled: bool=True
    advanced_controls_enabled: bool=True

@dataclass(frozen=True)
class HistoricalAnalysisRunRequest:
    underlying:str; instrument_key:str; start_date:date; end_date:date; interval_minutes:int=1
    analysis_cadence_minutes:int=5; include_historical_options:bool=True; download_missing_only:bool=True
    rebuild_intelligence:bool=False; rebuild_outcomes:bool=False; rebuild_index:bool=False
    requested_at:datetime|None=None
    def validate(self,settings,supported,today=None):
        if self.underlying not in supported or supported[self.underlying]!=self.instrument_key: raise ValueError("The selected instrument is not supported.")
        HistoricalRangeRequest(self.underlying,self.instrument_key,self.start_date,self.end_date,self.interval_minutes).validate(MarketLakeSettings(maximum_sync_range=settings.maximum_date_range_days),today=today)
    def range_request(self,day=None):
        return HistoricalRangeRequest(self.underlying,self.instrument_key,day or self.start_date,day or self.end_date,self.interval_minutes,
            include_options=self.include_historical_options,rebuild_raw=not self.download_missing_only,
            rebuild_intelligence=self.rebuild_intelligence,rebuild_outcomes=self.rebuild_outcomes)

@dataclass(frozen=True)
class DatePipelineStatus:
    trading_date:date; session:str="EXPECTED_WEEKDAY"; underlying:str="Pending"; options:str="Pending"
    intelligence:str="Pending"; outcomes:str="Pending"; index:str="Not indexed"; final:str="Pending"
    explanation:str="Waiting"

@dataclass(frozen=True)
class HistoricalPipelineProgress:
    run_id:str; overall_status:str; stage:str; stage_status:str; overall_percent:float; stage_percent:float
    current_date:date|None; current_item:str|None; status_message:str; expected_dates:int
    underlying_total:int=0; underlying_complete:int=0; option_total:int=0; option_complete:int=0; option_partial:int=0
    intelligence_total:int=0; intelligence_complete:int=0; outcome_total:int=0; outcome_complete:int=0
    index_total:int=0; index_complete:int=0; index_failed:int=0; index_outdated:int=0
    downloaded_rows:int=0; stored_rows:int=0
    completed_dates:tuple[date,...]=(); partial_dates:tuple[date,...]=(); failed_dates:tuple[date,...]=()
    skipped_dates:tuple[date,...]=(); date_statuses:tuple[DatePipelineStatus,...]=(); quality_flags:tuple[str,...]=()
    explanations:tuple[str,...]=(); option_expiries:int=0; option_contracts_total:int=0
    option_contracts_complete:int=0; option_contracts_failed:int=0; option_oi_coverage:float|None=None
    option_volume_coverage:float|None=None; option_ce_total:int=0; option_pe_total:int=0
    def __post_init__(self):
        object.__setattr__(self,"overall_percent",min(100.,max(0.,self.overall_percent)))
        object.__setattr__(self,"stage_percent",min(100.,max(0.,self.stage_percent)))

@dataclass(frozen=True)
class HistoricalAnalysisRunResult:
    run_id:str; status:str; progress:HistoricalPipelineProgress; analytics:Any=None
    started_at:datetime|None=None; completed_at:datetime|None=None

@dataclass(frozen=True)
class HistoricalAnalysisRunState:
    run_id:str; request:HistoricalAnalysisRunRequest; stage:str; status:str; created_at:datetime; updated_at:datetime
    completed_at:datetime|None=None; current_date:date|None=None; cancel_requested:bool=False
    completed_dates:tuple[date,...]=(); partial_dates:tuple[date,...]=(); failed_dates:tuple[date,...]=()
    skipped_dates:tuple[date,...]=(); quality_flags:tuple[str,...]=(); explanations:tuple[str,...]=()

class JsonRunCheckpointStore:
    SCHEMA_VERSION=2
    def __init__(self,root): self.root=Path(root)
    def save(self,request,progress):
        self.root.mkdir(parents=True,exist_ok=True); path=self.root/f"{progress.run_id}.json"; temporary=self.root/f".{progress.run_id}.tmp"
        payload={"schema_version":self.SCHEMA_VERSION,"request":asdict(request),"progress":asdict(progress)}
        temporary.write_text(json.dumps(payload,default=lambda value:value.isoformat(),sort_keys=True),encoding="utf-8"); temporary.replace(path)
    def load(self,run_id):
        path=self.root/f"{run_id}.json"
        try: payload=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as error: raise ValueError("Historical run checkpoint is unavailable or malformed.") from error
        if payload.get("schema_version")!=self.SCHEMA_VERSION: raise ValueError("Historical run checkpoint schema is unsupported.")
        try:
            raw=dict(payload["request"]); raw["start_date"]=date.fromisoformat(raw["start_date"]); raw["end_date"]=date.fromisoformat(raw["end_date"])
            if raw.get("requested_at"): raw["requested_at"]=datetime.fromisoformat(raw["requested_at"])
            request=HistoricalAnalysisRunRequest(**raw); data=dict(payload["progress"])
            data["current_date"]=date.fromisoformat(data["current_date"]) if data.get("current_date") else None
            for key in ("completed_dates","partial_dates","failed_dates","skipped_dates"): data[key]=tuple(date.fromisoformat(v) for v in data.get(key,()))
            data["date_statuses"]=tuple(DatePipelineStatus(**{**row,"trading_date":date.fromisoformat(row["trading_date"])}) for row in data.get("date_statuses",()))
            allowed={item.name for item in fields(HistoricalPipelineProgress)}
            return request,HistoricalPipelineProgress(**{k:v for k,v in data.items() if k in allowed})
        except (KeyError,TypeError,ValueError) as error: raise ValueError("Historical run checkpoint content is invalid.") from error
    def list_incomplete_runs(self):
        runs=[]
        for path in sorted(self.root.glob("*.json")) if self.root.exists() else ():
            try:
                _,progress=self.load(path.stem)
                if progress.overall_status != "COMPLETE": runs.append(path.stem)
            except ValueError: continue
        return tuple(runs)

def _dates(value,name):
    return {item if isinstance(item,date) else date.fromisoformat(str(item)) for item in (getattr(value,name,()) or ())}
def _count(value,*names):
    for name in names:
        item=getattr(value,name,None)
        if item is not None:
            try:return int(item)
            except (TypeError,ValueError): pass
    return 0

class HistoricalAnalysisOrchestrator:
    """Per-date coordinator which maps actual service results into durable state."""
    def __init__(self,*,sync_underlying,download_options=None,build_intelligence=None,build_outcomes=None,
                 build_index=None,prepare_analytics=None,checkpoint_store=None,settings=HistoricalAnalysisSettings(),should_cancel=None):
        self.operations={PipelineStage.DOWNLOAD_UNDERLYING:sync_underlying,PipelineStage.DOWNLOAD_OPTIONS:download_options,
            PipelineStage.BUILD_INTELLIGENCE:build_intelligence,PipelineStage.BUILD_OUTCOMES:build_outcomes,
            PipelineStage.BUILD_INDEX:build_index,PipelineStage.PREPARE_ANALYTICS:prepare_analytics}
        self.checkpoints=checkpoint_store; self.settings=settings; self.should_cancel=should_cancel or (lambda:False); self.cancel_requested=False
    def cancel_after_current_date(self): self.cancel_requested=True
    def _invoke(self,stage,request,day):
        operation=self.operations.get(stage)
        if operation is None:return None
        single=request.range_request(day)
        if stage is PipelineStage.BUILD_INTELLIGENCE:return operation(single,cadence_minutes=request.analysis_cadence_minutes)
        return operation(single)
    def run(self,request,*,progress_callback=None,run_id=None,resume=False,index_only=False):
        self.cancel_requested=False; started=datetime.now(timezone.utc); loaded=None
        if resume:
            if not run_id or not self.checkpoints: raise ValueError("A checkpointed run ID is required to resume.")
            saved_request,loaded=self.checkpoints.load(run_id)
            if saved_request!=request: request=saved_request
        run_id=run_id or uuid4().hex
        days=tuple(date.fromordinal(n) for n in range(request.start_date.toordinal(),request.end_date.toordinal()+1))
        if loaded: rows=list(loaded.date_statuses)
        else: rows=[DatePipelineStatus(d,"NOT_TRADING_SESSION",underlying="Not Trading Session",options="Not Trading Session",intelligence="Not Trading Session",outcomes="Not Trading Session",index="Not indexed",final="Skipped",explanation="Weekend") if d.weekday()>=5 else DatePipelineStatus(d) for d in days]
        active=[r.trading_date for r in rows if r.session!="NOT_TRADING_SESSION"]
        downloaded=loaded.downloaded_rows if loaded else 0; stored=loaded.stored_rows if loaded else 0
        option_stats=[0,0,0,0,0,0]; option_oi=None; option_volume=None; index_outdated=0
        analytics=None; last_percent=loaded.overall_percent if loaded else 0.
        enabled=[PipelineStage.BUILD_INDEX] if index_only else [PipelineStage.DOWNLOAD_UNDERLYING,PipelineStage.DOWNLOAD_OPTIONS,PipelineStage.BUILD_INTELLIGENCE,PipelineStage.BUILD_OUTCOMES,PipelineStage.BUILD_INDEX]
        total=1+sum(len(active) for stage in enabled if self.operations.get(stage) is not None and not(stage is PipelineStage.DOWNLOAD_OPTIONS and not request.include_historical_options))+1
        done=1
        def update(day,**changes):
            index=next(i for i,row in enumerate(rows) if row.trading_date==day); rows[index]=replace(rows[index],**changes)
        def ready(row):
            if row.underlying in {"Provider No Data","Failed"} or row.intelligence=="Intelligence Failed": return "Retry Required"
            if row.intelligence=="Intelligence Complete" and row.outcomes in {"Outcomes Complete","Outcomes Not Evaluable","Outcomes Pending"}:
                return "Ready" if row.options in {"Available","Partial Options"} else "Candle-only"
            return row.final
        def emit(stage,status,message,current=None,stage_done=0,stage_total=0):
            nonlocal last_percent
            completed=tuple(r.trading_date for r in rows if ready(r) in {"Ready","Candle-only"}); failed=tuple(r.trading_date for r in rows if ready(r)=="Retry Required")
            partial=tuple(r.trading_date for r in rows if r.options=="Partial Options" or r.index=="Index Failed")
            skipped=tuple(r.trading_date for r in rows if r.final=="Skipped")
            last_percent=max(last_percent,100.*done/max(1,total)); refreshed=tuple(replace(r,final=ready(r)) for r in rows)
            p=HistoricalPipelineProgress(run_id,status,stage.value,status,last_percent,100.*stage_done/max(1,stage_total),current,
                str(current) if current else None,message,len(days),len(active),sum(r.underlying in {"Existing","Downloaded"} for r in rows),
                len(active) if request.include_historical_options else 0,sum(r.options=="Available" for r in rows),sum(r.options=="Partial Options" for r in rows),
                len(active),sum(r.intelligence=="Intelligence Complete" for r in rows),len(active),sum(r.outcomes in {"Outcomes Complete","Outcomes Not Evaluable"} for r in rows),
                len(active),sum(r.index=="Indexed" for r in rows),sum(r.index=="Index Failed" for r in rows),index_outdated,
                downloaded,stored,completed,partial,failed,skipped,refreshed,
                option_expiries=option_stats[0],option_contracts_total=option_stats[1],option_contracts_complete=option_stats[2],option_contracts_failed=option_stats[3],
                option_oi_coverage=option_oi,option_volume_coverage=option_volume,
                option_ce_total=option_stats[4],option_pe_total=option_stats[5])
            if self.checkpoints and self.settings.checkpoint_enabled:self.checkpoints.save(request,p)
            if progress_callback:progress_callback(p)
            return p
        progress=emit(PipelineStage.PLAN,"COMPLETE",f"Prepared {len(days)} requested dates.",stage_done=len(days),stage_total=len(days))
        for stage in enabled:
            operation=self.operations.get(stage)
            if operation is None or (stage is PipelineStage.DOWNLOAD_OPTIONS and not request.include_historical_options): continue
            candidates=[]
            for row in rows:
                if row.trading_date not in active:continue
                if stage is PipelineStage.DOWNLOAD_UNDERLYING and row.underlying in {"Existing","Downloaded"}:continue
                if stage is PipelineStage.DOWNLOAD_OPTIONS and row.options in {"Available","Partial Options","Options Unavailable"}:continue
                if stage is PipelineStage.BUILD_INTELLIGENCE and (row.underlying not in {"Existing","Downloaded"} or (row.intelligence=="Intelligence Complete" and not request.rebuild_intelligence)):continue
                if stage is PipelineStage.BUILD_OUTCOMES and (row.intelligence!="Intelligence Complete" or (row.outcomes in {"Outcomes Complete","Outcomes Not Evaluable"} and not request.rebuild_outcomes)):continue
                if stage is PipelineStage.BUILD_INDEX and (row.intelligence!="Intelligence Complete" or (row.index=="Indexed" and not request.rebuild_index)):continue
                candidates.append(row.trading_date)
            for number,day in enumerate(candidates,1):
                try:
                    value=self._invoke(stage,request,day)
                    if stage is PipelineStage.DOWNLOAD_UNDERLYING:
                        downloaded+=_count(value,"downloaded_row_count"); stored+=_count(value,"stored_row_count")
                        if day in _dates(value,"completed_dates"):update(day,underlying="Downloaded",session="CONFIRMED_TRADING_SESSION",explanation="Underlying candles downloaded")
                        elif day in _dates(value,"skipped_dates"):update(day,underlying="Existing",session="CONFIRMED_TRADING_SESSION",explanation="Existing candles reused")
                        elif day in _dates(value,"no_data_dates"):update(day,underlying="Provider No Data",session="PROVIDER_NO_DATA",explanation="Provider returned no candles")
                        else:update(day,underlying="Failed",explanation="Underlying download failed")
                    elif stage is PipelineStage.DOWNLOAD_OPTIONS:
                        non_null_oi=getattr(value,"oi_coverage",None); non_null_volume=getattr(value,"volume_coverage",None)
                        if non_null_oi is not None: option_oi=float(non_null_oi)
                        if non_null_volume is not None: option_volume=float(non_null_volume)
                        option_stats[0]+=_count(value,"expiries_discovered"); option_stats[1]+=_count(value,"contracts_discovered"); option_stats[2]+=_count(value,"contracts_stored"); option_stats[3]+=_count(value,"failed_contracts")
                        option_stats[4]+=_count(value,"ce_contracts","ce_count"); option_stats[5]+=_count(value,"pe_contracts","pe_count")
                        complete=_count(value,"contracts_stored"); failures=_count(value,"failed_contracts")
                        partial_dates=_dates(value,"partial_dates"); failed_dates=_dates(value,"failed_dates")
                        completed_dates=_dates(value,"completed_dates")
                        option_status=("Partial Options" if day in partial_dates or (complete and failures) else
                            "Available" if day in completed_dates or complete else "Options Unavailable")
                        if day in failed_dates and not complete: option_status="Options Unavailable"
                        update(day,options=option_status,explanation="Historical option candles evaluated")
                    elif stage is PipelineStage.BUILD_INTELLIGENCE:
                        complete=(day in _dates(value,"completed_dates") or day in _dates(value,"skipped_dates")
                            or bool(value and not hasattr(value,"completed_dates")))
                        update(day,intelligence="Intelligence Complete" if complete else "Intelligence Failed",explanation="Point-in-time intelligence built" if complete else "Intelligence build failed")
                    elif stage is PipelineStage.BUILD_OUTCOMES:
                        if hasattr(value,"records"): records=tuple(value.records or ())
                        else:
                            try: records=tuple(value or ())
                            except TypeError: records=()
                        statuses={str(getattr(item,"status",getattr(item,"outcome_classification",""))).upper() for item in records}
                        completed_dates=_dates(value,"completed_dates"); pending_dates=_dates(value,"pending_dates")
                        not_evaluable_dates=_dates(value,"not_evaluable_dates"); failed_dates=_dates(value,"failed_dates")
                        if day in not_evaluable_dates:update(day,outcomes="Outcomes Not Evaluable",explanation="Outcome lacks required future data")
                        elif day in pending_dates or day in failed_dates or not records:update(day,outcomes="Outcomes Pending",explanation="Future candles are pending")
                        elif day in completed_dates:update(day,outcomes="Outcomes Complete",explanation="Factual outcomes stored")
                        elif "NOT_EVALUABLE" in statuses:update(day,outcomes="Outcomes Not Evaluable",explanation="Outcome lacks required future data")
                        else:update(day,outcomes="Outcomes Complete",explanation="Factual outcomes stored")
                    elif stage is PipelineStage.BUILD_INDEX:
                        index_outdated+=_count(value,"outdated","outdated_records")
                        if _count(value,"failed")>0:update(day,index="Index Failed",explanation="Source ready; similarity index unavailable")
                        elif _count(value,"completed","skipped")>=0:update(day,index="Indexed",explanation="Historical index current")
                except Exception as error:
                    if stage is PipelineStage.DOWNLOAD_OPTIONS:update(day,options="Options Unavailable",explanation=str(error) or "Options unavailable")
                    elif stage is PipelineStage.BUILD_INTELLIGENCE:update(day,intelligence="Intelligence Failed",explanation=str(error) or "Intelligence failed")
                    elif stage is PipelineStage.BUILD_OUTCOMES:update(day,outcomes="Outcomes Pending",explanation=str(error) or "Outcomes pending")
                    elif stage is PipelineStage.BUILD_INDEX:update(day,index="Index Failed",explanation=str(error) or "Index failed")
                    else:update(day,underlying="Failed",explanation=str(error) or "Download failed")
                done+=1; progress=emit(stage,"RUNNING",stage.value.replace("_"," ").title(),day,number,len(candidates))
                if self.cancel_requested or self.should_cancel():
                    progress=emit(stage,"CANCELLED","Cancelled after the current date; completed work was preserved.",day,number,len(candidates))
                    return HistoricalAnalysisRunResult(run_id,"CANCELLED",progress,started_at=started)
        if not index_only and self.operations.get(PipelineStage.PREPARE_ANALYTICS):
            analytics=self.operations[PipelineStage.PREPARE_ANALYTICS](request.range_request()); done+=1
            progress=emit(PipelineStage.PREPARE_ANALYTICS,"COMPLETE","Historical results prepared.",stage_done=1,stage_total=1)
        status="PARTIAL" if any(ready(r)=="Retry Required" or r.index=="Index Failed" for r in rows) else "COMPLETE"
        # Blocked units are resolved (not silently counted as successful), so a
        # finished run reaches 100% while its PARTIAL/date statuses retain truth.
        done=total
        progress=emit(PipelineStage.COMPLETE,status,"Results ready." if analytics is not None else "Processing complete.",stage_done=1,stage_total=1)
        return HistoricalAnalysisRunResult(run_id,status,progress,analytics,started,datetime.now(timezone.utc))
    def retry_failed_dates(self,request,run_id,**kwargs): return self.run(request,run_id=run_id,resume=True,**kwargs)
    def retry_index_only(self,request,run_id,**kwargs): return self.run(request,run_id=run_id,resume=True,index_only=True,**kwargs)
