"""Reliable, resumable one-click Historical Analysis orchestration."""
from __future__ import annotations
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from .market_lake import HistoricalRangeRequest, MarketLakeSettings
from .historical_pipeline_observability import HistoricalPipelineObserver, generate_run_id

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
    historical_log_root: str="logs/historical"; stall_threshold_seconds: float=60.0

@dataclass(frozen=True)
class HistoricalAnalysisRunRequest:
    underlying:str; instrument_key:str; start_date:date; end_date:date; interval_minutes:int=1
    analysis_cadence_minutes:int=5; include_historical_options:bool=True; download_missing_only:bool=True
    rebuild_intelligence:bool=False; rebuild_outcomes:bool=False; rebuild_index:bool=False
    rebuild_historical_options:bool=False
    requested_at:datetime|None=None
    def validate(self,settings,supported,today=None):
        if self.underlying not in supported or supported[self.underlying]!=self.instrument_key: raise ValueError("The selected instrument is not supported.")
        HistoricalRangeRequest(self.underlying,self.instrument_key,self.start_date,self.end_date,self.interval_minutes).validate(MarketLakeSettings(maximum_sync_range=settings.maximum_date_range_days),today=today)
    def range_request(self,day=None):
        return HistoricalRangeRequest(self.underlying,self.instrument_key,day or self.start_date,day or self.end_date,self.interval_minutes,
            include_options=self.include_historical_options,rebuild_raw=not self.download_missing_only,
            rebuild_intelligence=self.rebuild_intelligence,rebuild_outcomes=self.rebuild_outcomes,
            rebuild_options=self.rebuild_historical_options)

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
    last_completed_stage:str="—"; last_successful_date:date|None=None; elapsed_seconds:float=0.0
    last_exception:str="—"; stage_durations:tuple[tuple[str,float],...]=(); checkpoint_path:str="—"
    resume_available:bool=False
    def __post_init__(self):
        object.__setattr__(self,"overall_percent",min(100.,max(0.,self.overall_percent)))
        object.__setattr__(self,"stage_percent",min(100.,max(0.,self.stage_percent)))

@dataclass(frozen=True)
class HistoricalAnalysisRunResult:
    run_id:str; status:str; progress:HistoricalPipelineProgress; analytics:Any=None
    started_at:datetime|None=None; completed_at:datetime|None=None
    diagnostics:Any=None

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
                 build_index=None,prepare_analytics=None,checkpoint_store=None,settings=HistoricalAnalysisSettings(),should_cancel=None,
                 observer_factory=HistoricalPipelineObserver):
        self.operations={PipelineStage.DOWNLOAD_UNDERLYING:sync_underlying,PipelineStage.DOWNLOAD_OPTIONS:download_options,
            PipelineStage.BUILD_INTELLIGENCE:build_intelligence,PipelineStage.BUILD_OUTCOMES:build_outcomes,
            PipelineStage.BUILD_INDEX:build_index,PipelineStage.PREPARE_ANALYTICS:prepare_analytics}
        self.checkpoints=checkpoint_store; self.settings=settings; self.should_cancel=should_cancel or (lambda:False); self.cancel_requested=False
        self.observer_factory=observer_factory
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
        run_id=run_id or generate_run_id()
        checkpoint_path=(self.checkpoints.root/f"{run_id}.json") if self.checkpoints else None
        observer=self.observer_factory(run_id,log_root=self.settings.historical_log_root,
            checkpoint_path=checkpoint_path,stall_threshold_seconds=self.settings.stall_threshold_seconds)
        observer.log("orchestrator.run started", resume=resume, index_only=index_only)
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
                base="Ready" if row.options in {"Available","Partial","Existing"} else "Candle-only"
                if row.index=="Index Failed": return f"{base} — Similarity unavailable"
                if row.index in {"Index Pending","Not indexed"}: return "Partial"
                return base
            return row.final
        def emit(stage,status,message,current=None,stage_done=0,stage_total=0):
            nonlocal last_percent
            completed=tuple(r.trading_date for r in rows if ready(r) in {"Ready","Candle-only"}); failed=tuple(r.trading_date for r in rows if ready(r)=="Retry Required")
            partial=tuple(r.trading_date for r in rows if r.options=="Partial" or r.index in {"Index Failed","Index Pending"})
            skipped=tuple(r.trading_date for r in rows if r.final=="Skipped")
            last_percent=max(last_percent,100.*done/max(1,total)); refreshed=tuple(replace(r,final=ready(r)) for r in rows)
            p=HistoricalPipelineProgress(run_id,status,stage.value,status,last_percent,100.*stage_done/max(1,stage_total),current,
                str(current) if current else None,message,len(days),len(active),sum(r.underlying in {"Existing","Downloaded"} for r in rows),
                len(active),sum(r.options in {"Available","Existing","Skipped","Unavailable","Previously Unavailable","Failed Non-blocking"} for r in rows),sum(r.options=="Partial" for r in rows),
                len(active),sum(r.intelligence=="Intelligence Complete" for r in rows),len(active),sum(r.outcomes in {"Outcomes Complete","Outcomes Not Evaluable"} for r in rows),
                len(active),sum(r.index=="Indexed" for r in rows),sum(r.index=="Index Failed" for r in rows),index_outdated,
                downloaded,stored,completed,partial,failed,skipped,refreshed,
                option_expiries=option_stats[0],option_contracts_total=option_stats[1],option_contracts_complete=option_stats[2],option_contracts_failed=option_stats[3],
                option_oi_coverage=option_oi,option_volume_coverage=option_volume,
                option_ce_total=option_stats[4],option_pe_total=option_stats[5],
                last_completed_stage=observer.diagnostics.last_completed_stage,
                last_successful_date=observer.diagnostics.last_successful_date,
                elapsed_seconds=observer.diagnostics.elapsed_time,last_exception=observer.diagnostics.last_exception,
                stage_durations=tuple(observer.diagnostics.stage_durations.items()),
                checkpoint_path=observer.diagnostics.checkpoint_path,
                resume_available=bool(self.checkpoints and self.settings.resume_enabled))
            observer.diagnostics.current_progress=p.overall_percent
            observer.diagnostics.completed_dates=p.completed_dates; observer.diagnostics.failed_dates=p.failed_dates
            observer.diagnostics.skipped_dates=p.skipped_dates; observer.diagnostics.partial_dates=p.partial_dates
            if self.checkpoints and self.settings.checkpoint_enabled:self.checkpoints.save(request,p)
            if progress_callback:progress_callback(p)
            return p
        observer.stage_started(PipelineStage.PLAN.value,days)
        for row in rows:
            observer.date_status(row.trading_date,PipelineStage.PLAN.value,
                "skipped" if row.session=="NOT_TRADING_SESSION" else "planned")
        progress=emit(PipelineStage.PLAN,"RUNNING","Planning trading sessions...",stage_done=len(days),stage_total=len(days))
        observer.stage_completed(PipelineStage.PLAN.value,days)
        progress=emit(PipelineStage.PLAN,"COMPLETE",f"Prepared {len(days)} requested dates.",stage_done=len(days),stage_total=len(days))
        for stage in enabled:
            operation=self.operations.get(stage)
            if operation is None or (stage is PipelineStage.DOWNLOAD_OPTIONS and not request.include_historical_options):
                reason="operation unavailable" if operation is None else "historical options disabled by request"
                observer.stage_started(stage.value,active); observer.log(f"{stage.value} skipped",reason=reason)
                for day in active:
                    if stage is PipelineStage.DOWNLOAD_OPTIONS:
                        option_status="Unavailable" if operation is None else "Skipped"
                        update(day,options=option_status,explanation=("Historical option service unavailable; candle-only replay"
                            if operation is None else "Historical options disabled; candle-only replay"))
                    observer.date_status(day,stage.value,"UNAVAILABLE" if operation is None else "SKIPPED",
                        reason=reason,final_status="OPTION_DATA_UNAVAILABLE" if operation is None else "SKIPPED")
                observer.stage_completed(stage.value,active)
                if stage is PipelineStage.DOWNLOAD_OPTIONS:
                    terminal="UNAVAILABLE" if operation is None else "SKIPPED"
                    progress=emit(stage,terminal,"Historical options terminated; continuing with candle-only replay.",stage_done=len(active),stage_total=len(active))
                continue
            candidates=[]
            for row in rows:
                if row.trading_date not in active:continue
                if stage is PipelineStage.DOWNLOAD_UNDERLYING and row.underlying in {"Existing","Downloaded"}:continue
                if stage is PipelineStage.DOWNLOAD_OPTIONS and row.options in {"Available","Existing","Partial","Unavailable","Previously Unavailable","Skipped","Failed Non-blocking"} and not request.rebuild_historical_options:continue
                if stage is PipelineStage.BUILD_INTELLIGENCE and (row.underlying not in {"Existing","Downloaded"} or (row.intelligence=="Intelligence Complete" and not request.rebuild_intelligence)):continue
                if stage is PipelineStage.BUILD_OUTCOMES and (row.intelligence!="Intelligence Complete" or (row.outcomes in {"Outcomes Complete","Outcomes Not Evaluable"} and not request.rebuild_outcomes)):continue
                if stage is PipelineStage.BUILD_INDEX and (row.intelligence!="Intelligence Complete" or (row.index=="Indexed" and not request.rebuild_index)):continue
                candidates.append(row.trading_date)
            observer.stage_started(stage.value,candidates)
            stage_messages={PipelineStage.DOWNLOAD_UNDERLYING:"Checking existing Market Lake data...",
                PipelineStage.DOWNLOAD_OPTIONS:"Downloading option history...",
                PipelineStage.BUILD_INTELLIGENCE:"Building ITOS intelligence...",
                PipelineStage.BUILD_OUTCOMES:"Building historical outcomes...",
                PipelineStage.BUILD_INDEX:"Updating historical index..."}
            progress=emit(stage,"RUNNING",stage_messages[stage],stage_total=len(candidates))
            for number,day in enumerate(candidates,1):
                operation_started=datetime.now(timezone.utc)
                try:
                    if stage is PipelineStage.DOWNLOAD_OPTIONS:
                        observer.log(
                            "option request",
                            date=day,
                            current_request="historical option enrichment",
                        )
                        observer.log(
                            "calling download_options",
                            date=day,
                        )
                    elif stage is PipelineStage.BUILD_INTELLIGENCE:
                        observer.log("BUILD_INTELLIGENCE started", date=day)

                    value = self._invoke(stage, request, day)

                    if stage is PipelineStage.DOWNLOAD_OPTIONS:
                        observer.log(
                            "returned from download_options",
                            date=day,
                            result_type=type(value).__name__ if value is not None else "None",
                        )
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
                        result_status = str(getattr(value, "status", ""))
                        if result_status == "OPTION_DATA_EXISTING":
                            option_status = "Existing"
                            explanation = "Existing historical option coverage reused"
                        elif result_status == "OPTION_DATA_PREVIOUSLY_UNAVAILABLE":
                            option_status = "Previously Unavailable"
                            explanation = "Previously confirmed provider-unavailable option data reused"
                        else:
                            option_status=("Partial" if day in partial_dates or (complete and failures) else
                                "Available" if day in completed_dates or complete else "Unavailable")
                            if day in failed_dates and not complete: option_status="Unavailable"
                            explanation = "Historical option candles evaluated"
                        update(day,options=option_status,explanation=explanation)
                        terminal=("PARTIAL" if option_status=="Partial" else "COMPLETE" if option_status in {"Available","Existing"}
                            else "UNAVAILABLE")
                        observer.log("option request completed",date=day,expiries=option_stats[0],contracts=option_stats[1],
                            elapsed_seconds=f"{(datetime.now(timezone.utc)-operation_started).total_seconds():.3f}",reason=getattr(value,"status","OPTION_DATA_UNAVAILABLE"),final_status=terminal)
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
                        index_failed=_count(value,"failed")
                        index_completed=_count(value,"completed")
                        index_skipped=_count(value,"skipped")
                        if index_failed>0:update(day,index="Index Failed",explanation="Source ready; similarity index unavailable")
                        elif index_completed>0 or index_skipped>0:update(day,index="Indexed",explanation="Historical index current")
                        else:update(day,index="Index Pending",explanation="No index records were built or confirmed current")
                    current_row=next(row for row in rows if row.trading_date==day)
                    status={PipelineStage.DOWNLOAD_UNDERLYING:current_row.underlying,
                        PipelineStage.DOWNLOAD_OPTIONS:current_row.options,PipelineStage.BUILD_INTELLIGENCE:current_row.intelligence,
                        PipelineStage.BUILD_OUTCOMES:current_row.outcomes,PipelineStage.BUILD_INDEX:current_row.index}[stage]
                    observer.diagnostics.last_successful_date=day
                    observer.date_status(day,stage.value,status,rows_stored=_count(value,"stored_row_count"),
                        rows_skipped=_count(value,"skipped_row_count"),option_coverage=getattr(value,"oi_coverage",None),
                        analysis_points=_count(value,"completed","analysis_points"),outcomes_built=len(records) if stage is PipelineStage.BUILD_OUTCOMES else 0,
                        index_records=_count(value,"completed") if stage is PipelineStage.BUILD_INDEX else 0)
                except Exception as error:
                    observer.stage_failed(stage.value,error,day=day)
                    if stage is PipelineStage.DOWNLOAD_OPTIONS:update(day,options="Failed Non-blocking",explanation=f"{type(error).__name__}; candle-only replay")
                    elif stage is PipelineStage.BUILD_INTELLIGENCE:update(day,intelligence="Intelligence Failed",explanation=str(error) or "Intelligence failed")
                    elif stage is PipelineStage.BUILD_OUTCOMES:update(day,outcomes="Outcomes Pending",explanation=str(error) or "Outcomes pending")
                    elif stage is PipelineStage.BUILD_INDEX:update(day,index="Index Failed",explanation=str(error) or "Index failed")
                    else:update(day,underlying="Failed",explanation=str(error) or "Download failed")
                    observer.date_status(day,stage.value,"FAILED_NON_BLOCKING" if stage is PipelineStage.DOWNLOAD_OPTIONS else "failed",
                        reason=type(error).__name__)
                done+=1; progress=emit(stage,"RUNNING",stage.value.replace("_"," ").title(),day,number,len(candidates))
                observer.validate_stall(stage.value,day,(datetime.now(timezone.utc)-operation_started).total_seconds(),f"date {day}")
                if self.cancel_requested or self.should_cancel():
                    progress=emit(stage,"CANCELLED","Cancelled after the current date; completed work was preserved.",day,number,len(candidates))
                    observer.log("orchestrator.run() returned",status="CANCELLED"); observer.close()
                    return HistoricalAnalysisRunResult(run_id,"CANCELLED",progress,started_at=started,diagnostics=observer.diagnostics)
            observer.stage_completed(stage.value,candidates)
            if stage is PipelineStage.DOWNLOAD_OPTIONS:
                statuses={next(row for row in rows if row.trading_date==day).options for day in candidates}
                terminal="PARTIAL" if "Partial" in statuses else "COMPLETE" if statuses=={"Available"} else "FAILED_NON_BLOCKING" if "Failed Non-blocking" in statuses else "UNAVAILABLE"
                progress=emit(stage,terminal,"Historical option enrichment finished; continuing to ITOS Intelligence.",stage_done=len(candidates),stage_total=len(candidates))
        if not index_only and self.operations.get(PipelineStage.PREPARE_ANALYTICS):
            observer.stage_started(PipelineStage.PREPARE_ANALYTICS.value,active)
            progress=emit(PipelineStage.PREPARE_ANALYTICS,"RUNNING","Preparing Historical Results...",stage_total=1)
            try: analytics=self.operations[PipelineStage.PREPARE_ANALYTICS](request.range_request())
            except Exception as error:
                observer.stage_failed(PipelineStage.PREPARE_ANALYTICS.value,error); observer.close(); raise
            done+=1; observer.stage_completed(PipelineStage.PREPARE_ANALYTICS.value,active)
            progress=emit(PipelineStage.PREPARE_ANALYTICS,"COMPLETE","Historical results prepared.",stage_done=1,stage_total=1)
        elif not index_only:
            observer.stage_started(PipelineStage.PREPARE_ANALYTICS.value,active)
            observer.log("PREPARE_ANALYTICS skipped",reason="operation unavailable; analytics not executed")
            observer.stage_completed(PipelineStage.PREPARE_ANALYTICS.value,active)
        status="PARTIAL" if any(ready(r) in {"Retry Required","Partial"} or
            r.index=="Index Failed" for r in rows) else "COMPLETE"
        # Blocked units are resolved (not silently counted as successful), so a
        # finished run reaches 100% while its PARTIAL/date statuses retain truth.
        done=total
        observer.diagnostics.stage_durations["TOTAL"]=(datetime.now(timezone.utc)-started).total_seconds()
        progress=emit(PipelineStage.COMPLETE,status,"Results ready." if analytics is not None else "Processing complete.",stage_done=1,stage_total=1)
        observer.log("final_status",status=status); observer.log("orchestrator.run completed",status=status)
        observer.close()
        return HistoricalAnalysisRunResult(run_id,status,progress,analytics,started,datetime.now(timezone.utc),observer.diagnostics)
    def retry_failed_dates(self,request,run_id,**kwargs): return self.run(request,run_id=run_id,resume=True,**kwargs)
    def retry_index_only(self,request,run_id,**kwargs): return self.run(request,run_id=run_id,resume=True,index_only=True,**kwargs)
