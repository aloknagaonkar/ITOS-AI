"""Failure-isolated, scheduler-ready Live capture and finalization services."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping, Sequence
import pandas as pd

from .market_lake import HistoricalIntelligenceRecord, HistoricalOutcomeService, IntelligenceQuery, LocalHistoricalMarketLake

SECRET_KEYS = frozenset({"access_token","authorization","token","client_secret","refresh_token"})

def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping): return {k:_sanitize(v) for k,v in value.items() if str(k).lower() not in SECRET_KEYS and "token" not in str(k).lower()}
    if isinstance(value, (list,tuple)): return [_sanitize(v) for v in value]
    if isinstance(value, (str,int,float,bool)) or value is None: return value
    return None

@dataclass(frozen=True)
class LiveCaptureSettings:
    enabled: bool = True; cadence_minutes: int = 5

@dataclass(frozen=True)
class LiveCaptureStatus:
    enabled: bool; cadence_minutes: int; last_raw_snapshot_stored: datetime | None = None
    last_intelligence_record_stored: datetime | None = None; last_option_snapshot_stored: datetime | None = None
    pending_outcomes: int = 0; current_session_status: str = "PENDING"; finalization_status: str = "NOT_RUN"
    capture_errors: tuple[str,...] = ()

class LiveMarketLakeCaptureService:
    def __init__(self, lake: LocalHistoricalMarketLake, *, provider: str="upstox", settings: LiveCaptureSettings=LiveCaptureSettings()):
        self.lake,self.provider,self.settings=lake,provider,settings; self._keys=set(); self.status=LiveCaptureStatus(settings.enabled,settings.cadence_minutes)
    def capture(self, *, instrument_key: str, interval: int, timestamp: datetime, raw_snapshot: Mapping[str,Any], intelligence: HistoricalIntelligenceRecord, option_records: Sequence[Mapping[str,Any]]=()) -> bool:
        key=f"{instrument_key}|{interval}|{timestamp.isoformat()}|{intelligence.engine_version}"
        if not self.settings.enabled or key in self._keys: return False
        try:
            safe=_sanitize(raw_snapshot); price=safe.get("close",safe.get("spot")) if isinstance(safe,Mapping) else None
            frame=pd.DataFrame([{"timestamp":timestamp,"open":safe.get("open",price),"high":safe.get("high",price),"low":safe.get("low",price),"close":price,"volume":safe.get("volume"),"open_interest":safe.get("open_interest")}])
            self.lake.store_raw_candles(self.provider,instrument_key,interval,timestamp.date(),frame)
            self.lake.store_intelligence_records((intelligence,))
            option_stamp=None
            if option_records:
                expiry=next((date.fromisoformat(str(x.get("expiry"))) for x in option_records if x.get("expiry")),timestamp.date())
                self.lake.store_option_snapshots(self.provider,instrument_key,expiry,timestamp.date(),timestamp,tuple(_sanitize(x) for x in option_records)); option_stamp=timestamp
            self._keys.add(key); self.status=LiveCaptureStatus(True,self.settings.cadence_minutes,timestamp,timestamp,option_stamp,1,"CAPTURING","NOT_RUN",())
            return True
        except Exception:
            self.status=LiveCaptureStatus(True,self.settings.cadence_minutes,capture_errors=("Live Market Lake persistence failed.",))
            return False

@dataclass(frozen=True)
class FinalizationResult:
    trading_date: date; outcomes_built: int; session_complete: bool; status: str; diagnostics: tuple[str,...]=()

class AfterMarketFinalizationService:
    def __init__(self,lake:LocalHistoricalMarketLake,*,provider:str="upstox"): self.lake,self.provider=lake,provider
    def finalize(self,instrument_key:str,interval:int,trading_date:date,engine_version:str)->FinalizationResult:
        records=self.lake.query_intelligence(IntelligenceQuery(instrument_key,trading_date,trading_date,interval,engine_version=engine_version))
        if not records: return FinalizationResult(trading_date,0,False,"INCOMPLETE",("No stored intelligence for session.",))
        outcomes=HistoricalOutcomeService(self.lake,provider=self.provider).build(records)
        complete=bool(outcomes) and all(x.future_data_available for x in outcomes)
        manifest=self.lake.get_manifest(self.provider,instrument_key,interval)
        if manifest is not None:
            outcome_dates=set(manifest.outcome_dates)
            if complete: outcome_dates.add(trading_date)
            self.lake.put_manifest(replace(manifest,outcome_dates=tuple(sorted(outcome_dates)),
                explanations=tuple(sorted(set(manifest.explanations + (("After-market finalization complete.",) if complete else ("After-market finalization incomplete.",)))))))
        return FinalizationResult(trading_date,len(outcomes),complete,"COMPLETE" if complete else "INCOMPLETE",() if complete else ("Pending future candles remain.",))
