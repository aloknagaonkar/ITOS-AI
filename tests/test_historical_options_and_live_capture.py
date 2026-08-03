from datetime import date, datetime
import json
import logging
import pandas as pd

from itos_platform.historical_options import HistoricalOptionDownloadService
from itos_platform.live_market_lake import LiveMarketLakeCaptureService, AfterMarketFinalizationService
from itos_platform.market_lake import HistoricalIntelligenceRecord, LocalHistoricalMarketLake, MarketLakeSettings

STAMP=datetime(2026,7,10,10)
def record(values=None): return HistoricalIntelligenceRecord("upstox","NIFTY","NIFTY",1,STAMP.date(),STAMP,STAMP,STAMP,"engine","intelligence-v1","FULL_REPLAY","WAIT",50,50,values=values or {})
class FakeExpired:
 def get_expired_option_expiries(self,key): return ["2026-07-30"]
 def get_expired_option_contracts(self,key,expiry): return [{"expired_instrument_key":"expired|1","instrument_type":"CE","strike_price":25000}]
 def get_expired_historical_candles(self,key,start,end,interval): return pd.DataFrame([{"timestamp":"2026-07-10T10:00:00+05:30","open":10,"high":12,"low":9,"close":11,"volume":100,"oi":50}])

def test_expired_download_is_explicit_and_stores_partial_replay(tmp_path):
 lake=LocalHistoricalMarketLake(MarketLakeSettings(market_lake_root=tmp_path)); service=HistoricalOptionDownloadService(FakeExpired(),lake)
 result=service.download("NIFTY",date(2026,7,10),date(2026,7,10)); assert result.contracts_stored==1 and result.status=="PARTIAL_OPTION_COVERAGE"
 stored=lake.load_option_snapshots("upstox","NIFTY",date(2026,7,30),date(2026,7,10)); assert stored[0]["bid"] is None and stored[0]["greeks"] is None

def test_live_capture_raw_intelligence_option_idempotent_and_secret_free(tmp_path):
 lake=LocalHistoricalMarketLake(MarketLakeSettings(market_lake_root=tmp_path)); service=LiveMarketLakeCaptureService(lake)
 raw={"spot":100,"access_token":"SECRET","authorization":"Bearer SECRET"}; options=({"expiry":"2026-07-30","strike":100,"side":"CE","token":"SECRET"},)
 assert service.capture(instrument_key="NIFTY",interval=1,timestamp=STAMP,raw_snapshot=raw,intelligence=record(),option_records=options)
 assert not service.capture(instrument_key="NIFTY",interval=1,timestamp=STAMP,raw_snapshot=raw,intelligence=record(),option_records=options)
 assert "SECRET" not in "".join(p.read_text() for p in tmp_path.rglob("*.json"))
 assert service.status.last_raw_snapshot_stored==STAMP and service.status.last_option_snapshot_stored==STAMP

def test_live_persistence_failure_does_not_raise():
 class Broken:
  def store_raw_candles(self,*a): raise OSError
 service=LiveMarketLakeCaptureService(Broken()); assert service.capture(instrument_key="NIFTY",interval=1,timestamp=STAMP,raw_snapshot={"spot":1},intelligence=record()) is False
 assert service.status.capture_errors==("Live Market Lake persistence failed.",)

def test_finalization_incomplete_without_intelligence(tmp_path):
 lake=LocalHistoricalMarketLake(MarketLakeSettings(market_lake_root=tmp_path)); result=AfterMarketFinalizationService(lake).finalize("NIFTY",1,STAMP.date(),"engine")
 assert not result.session_complete and result.status=="INCOMPLETE"

def test_services_never_log_token(caplog,tmp_path):
 caplog.set_level(logging.DEBUG); lake=LocalHistoricalMarketLake(MarketLakeSettings(market_lake_root=tmp_path)); LiveMarketLakeCaptureService(lake).capture(instrument_key="NIFTY",interval=1,timestamp=STAMP,raw_snapshot={"spot":1,"access_token":"SECRET"},intelligence=record())
 assert "SECRET" not in caplog.text

def test_historical_option_timeout_is_configured_and_non_blocking(tmp_path):
 class TimeoutExpired(FakeExpired):
  def get_expired_option_expiries(self,key,*,timeout):
   assert timeout==3.5
   raise TimeoutError("access_token=SECRET")
 lake=LocalHistoricalMarketLake(MarketLakeSettings(market_lake_root=tmp_path))
 result=HistoricalOptionDownloadService(TimeoutExpired(),lake,request_timeout_seconds=3.5).download("NIFTY",STAMP.date(),STAMP.date())
 assert result.status=="OPTION_DATA_UNAVAILABLE" and result.contracts_stored==0
