"""Official expired-instrument candle adapter and derived-chain projection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import inspect
import logging
import time
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd

from .historical_sync import HistoricalMalformedResponseError, normalize_historical_candles
from .market_lake import LocalHistoricalMarketLake


class ExpiredOptionClient(Protocol):
    def get_expired_option_expiries(self, instrument_key: str, *, timeout: float | None = None) -> Sequence[str]: ...
    def get_expired_option_contracts(self, instrument_key: str, expiry_date: str, *, timeout: float | None = None) -> Sequence[Mapping[str, Any]]: ...
    def get_expired_historical_candles(self, expired_instrument_key: str, from_date: str, to_date: str, *, interval: int, timeout: float | None = None) -> pd.DataFrame: ...


@dataclass(frozen=True)
class HistoricalOptionDownloadResult:
    expiries_discovered: int; contracts_discovered: int; contracts_stored: int
    failed_contracts: int; status: str; explanations: tuple[str, ...] = ()
    completed_dates: tuple[date, ...] = ()
    skipped_dates: tuple[date, ...] = ()
    partial_dates: tuple[date, ...] = ()
    failed_dates: tuple[date, ...] = ()


class HistoricalOptionDownloadService:
    """Explicit, read-only provider workflow; construction never makes a request."""
    def __init__(self, client: ExpiredOptionClient, lake: LocalHistoricalMarketLake, *, provider: str = "upstox",
                 request_timeout_seconds: float = 20.0):
        if request_timeout_seconds <= 0: raise ValueError("request_timeout_seconds must be positive")
        self.client, self.lake, self.provider = client, lake, provider
        self.request_timeout_seconds = request_timeout_seconds

    def _request(self, method_name: str, *args, **kwargs):
        """Apply the configured HTTP timeout where the provider supports overrides."""
        method = getattr(self.client, method_name)
        if "timeout" in inspect.signature(method).parameters:
            kwargs["timeout"] = self.request_timeout_seconds
        return method(*args, **kwargs)

    def download(
        self, instrument_key: str, start_date: date, end_date: date, *,
        underlying: str | None = None, interval: int = 1, force: bool = False,
    ) -> HistoricalOptionDownloadResult:
        if start_date > end_date: raise ValueError("start_date must be on or before end_date")
        started=time.monotonic(); logger=logging.getLogger("historical_pipeline")
        requested_days = tuple(
            date.fromordinal(value)
            for value in range(start_date.toordinal(), end_date.toordinal() + 1)
        )
        if not force:
            states = {
                day: self.lake.option_download_status(self.provider, instrument_key, interval, day)
                for day in requested_days
            }
            if states and all(state in {"PARTIAL", "UNAVAILABLE"} for state in states.values()):
                partial = tuple(day for day, state in states.items() if state == "PARTIAL")
                unavailable = tuple(day for day, state in states.items() if state == "UNAVAILABLE")
                status = "OPTION_DATA_EXISTING" if partial else "OPTION_DATA_PREVIOUSLY_UNAVAILABLE"
                logger.info(
                    "option download skipped start_date=%s end_date=%s status=%s partial_dates=%s unavailable_dates=%s",
                    start_date, end_date, status, list(partial), list(unavailable),
                )
                return HistoricalOptionDownloadResult(
                    0, 0, 0, 0, status,
                    ("Historical option download reused durable Market Lake status.",),
                    skipped_dates=requested_days, partial_dates=partial,
                )
        logger.info("expiry discovery started date=%s", start_date)
        try: expiries = tuple(self._request("get_expired_option_expiries", instrument_key))
        except TimeoutError as error:
            logger.warning("expiry discovery timed out date=%s elapsed_seconds=%.3f final_status=UNAVAILABLE",
                start_date,time.monotonic()-started)
            return HistoricalOptionDownloadResult(0,0,0,0,"OPTION_DATA_UNAVAILABLE",(type(error).__name__,))
        except Exception as error:
            status=getattr(getattr(error,"response",None),"status_code",None)
            logger.warning("expiry discovery failed date=%s elapsed_seconds=%.3f reason=%s http_status=%s final_status=FAILED_NON_BLOCKING",
                start_date,time.monotonic()-started,type(error).__name__,status if isinstance(status,int) else "unavailable")
            return HistoricalOptionDownloadResult(0,0,0,0,"OPTION_DATA_UNAVAILABLE",(type(error).__name__,))
        logger.info("expiry discovery completed date=%s expiry_count=%d elapsed_seconds=%.3f",start_date,len(expiries),time.monotonic()-started)
        if not expiries:
            logger.info("option no-data date=%s reason=empty_expiry_discovery final_status=SKIPPED",start_date)
            result = HistoricalOptionDownloadResult(0,0,0,0,"OPTION_DATA_UNAVAILABLE",("No historical option expiries were available.",), skipped_dates=requested_days)
            for day in requested_days: self.lake.mark_option_download_status(self.provider, instrument_key, underlying or instrument_key, interval, day, "UNAVAILABLE")
            return result

        provider_expiry_count = len(expiries)
        maximum_expiry = end_date + timedelta(days=90)
        eligible_expiries = []
        invalid_expiries = 0
        for expiry_text in expiries:
            try:
                expiry = date.fromisoformat(str(expiry_text))
            except (TypeError, ValueError):
                invalid_expiries += 1
                continue
            if start_date <= expiry <= maximum_expiry:
                eligible_expiries.append(str(expiry_text))

        expiries = tuple(eligible_expiries)
        logger.info(
            "expiry filtering completed date=%s provider_expiry_count=%d eligible_expiry_count=%d "
            "invalid_expiry_count=%d maximum_expiry=%s skipped_expiry_count=%d",
            start_date,
            provider_expiry_count,
            len(expiries),
            invalid_expiries,
            maximum_expiry,
            provider_expiry_count - len(expiries),
        )
        if not expiries:
            logger.info(
                "option no-data date=%s reason=no_expiry_overlaps_requested_window "
                "maximum_expiry=%s final_status=SKIPPED",
                start_date,
                maximum_expiry,
            )
            result = HistoricalOptionDownloadResult(
                0, 0, 0, 0, "OPTION_DATA_UNAVAILABLE",
                ("No historical option expiry overlapped the requested trading window.",),
                skipped_dates=requested_days,
            )
            for day in requested_days:
                self.lake.mark_option_download_status(
                    self.provider, instrument_key, underlying or instrument_key, interval, day, "UNAVAILABLE"
                )
            return result

        discovered = stored = failed = 0
        contract_counts: dict[str, int] = {}
        empty_candle_responses = 0
        successful_candle_responses = 0
        contract_lookup_seconds = 0.0
        candle_download_seconds = 0.0
        storage_seconds = 0.0
        for expiry_text in expiries:
            logger.info("contract discovery started date=%s expiry=%s",start_date,expiry_text)
            try:
                expiry = date.fromisoformat(str(expiry_text))
                contract_lookup_started = time.monotonic()
                contracts = tuple(
                    self._request(
                        "get_expired_option_contracts",
                        instrument_key,
                        expiry_text,
                    )
                )
                contract_lookup_seconds += time.monotonic() - contract_lookup_started
                contract_counts[str(expiry_text)] = len(contracts)
            except (ValueError, TypeError): continue
            except TimeoutError:
                failed += 1
                logger.warning("contract discovery timed out date=%s expiry=%s",start_date,expiry_text)
                continue
            except Exception:
                failed += 1
                logger.exception("contract discovery failed date=%s expiry=%s",start_date,expiry_text,exc_info=False)
                continue
            logger.info("contract discovery completed date=%s expiry=%s contract_count=%d",start_date,expiry_text,len(contracts))
            if not contracts:
                logger.info("option no-data date=%s expiry=%s contracts=0 reason=no_contracts",start_date,expiry_text)
            for contract in contracts:
                discovered += 1
                key = contract.get("expired_instrument_key") or contract.get("instrument_key")
                side = str(contract.get("instrument_type") or contract.get("option_type") or "").upper()
                strike = contract.get("strike_price")
                if not key or side not in {"CE", "PE"} or strike is None: failed += 1; continue
                try:
                    logger.info("request started date=%s expiry=%s contract=%s",start_date,expiry_text,key)
                    candle_request_started = time.monotonic()
                    candles = normalize_historical_candles(
                        self._request(
                            "get_expired_historical_candles",
                            str(key),
                            start_date.isoformat(),
                            end_date.isoformat(),
                            interval=1,
                        )
                    )
                    candle_download_seconds += time.monotonic() - candle_request_started
                    if candles.empty:
                        empty_candle_responses += 1
                        failed += 1
                        logger.info("option no-data date=%s expiry=%s current_request=%s reason=provider_no_data",start_date,expiry_text,key)
                        continue
                    successful_candle_responses += 1
                    for day, frame in candles.groupby(candles["timestamp"].dt.date):
                        records = [{"timestamp": row.timestamp.isoformat(), "expiry": expiry.isoformat(), "strike": strike,
                            "side": side, "open": row.open, "high": row.high, "low": row.low, "close": row.close,
                            "ltp": row.close, "volume": row.volume if pd.notna(row.volume) else None,
                            "oi": row.open_interest if pd.notna(row.open_interest) else None,
                            "bid": None, "ask": None, "iv": None, "greeks": None,
                            "replay_completeness": "PARTIAL_OPTION_REPLAY"} for row in frame.itertuples()]
                        storage_started = time.monotonic()
                        self.lake.store_option_snapshots(
                            self.provider,
                            instrument_key,
                            expiry,
                            day,
                            frame.iloc[-1]["timestamp"].to_pydatetime(),
                            records,
                        )
                        storage_seconds += time.monotonic() - storage_started
                    stored += 1
                    logger.info("request completed date=%s expiry=%s contract=%s rows=%d",start_date,expiry_text,key,len(candles))
                except TimeoutError:
                    failed += 1
                    logger.warning("request timed out date=%s expiry=%s contract=%s",start_date,expiry_text,key)
                except HistoricalMalformedResponseError:
                    failed += 1
                    logger.warning("request failed date=%s expiry=%s contract=%s reason=malformed_response",start_date,expiry_text,key)
                except Exception:
                    failed += 1
                    logger.exception("request failed date=%s expiry=%s contract=%s",start_date,expiry_text,key,exc_info=False)
        logger.info(
            "option runtime measurement "
            "date=%s "
            "expiry_count=%d "
            "expiries=%s "
            "contracts_per_expiry=%s "
            "total_contracts=%d "
            "successful_candle_responses=%d "
            "empty_candle_responses=%d "
            "contract_lookup_seconds=%.3f "
            "candle_download_seconds=%.3f "
            "storage_seconds=%.3f "
            "total_elapsed_seconds=%.3f",
            start_date,
            len(expiries),
            list(expiries),
            contract_counts,
            discovered,
            successful_candle_responses,
            empty_candle_responses,
            contract_lookup_seconds,
            candle_download_seconds,
            storage_seconds,
            time.monotonic() - started,
        )
        status = "PARTIAL_OPTION_COVERAGE" if stored else "OPTION_DATA_UNAVAILABLE"
        logger.info("option download completed date=%s expiries=%d contracts=%d stored=%d failed=%d elapsed_seconds=%.3f final_status=%s",
            start_date,len(expiries),discovered,stored,failed,time.monotonic()-started,"PARTIAL" if stored else "FAILED_NON_BLOCKING")
        partial_days = tuple(sorted({day for day in requested_days if self.lake.option_download_status(
            self.provider, instrument_key, interval, day
        ) == "PARTIAL"}))
        if stored:
            for day in requested_days:
                if self.lake.option_download_status(self.provider, instrument_key, interval, day) is None:
                    self.lake.mark_option_download_status(
                        self.provider, instrument_key, underlying or instrument_key, interval, day, "PARTIAL"
                    )
            partial_days = requested_days
        elif not successful_candle_responses and (failed == 0 or (
            discovered and empty_candle_responses and failed == empty_candle_responses
        )):
            for day in requested_days:
                self.lake.mark_option_download_status(
                    self.provider, instrument_key, underlying or instrument_key, interval, day, "UNAVAILABLE"
                )
        return HistoricalOptionDownloadResult(
            len(expiries), discovered, stored, failed, status,
            ("Expired candles do not provide historical bid/ask, IV, or Greeks.",),
            completed_dates=requested_days if stored else (),
            partial_dates=partial_days if stored else (),
            skipped_dates=requested_days if (not stored and not successful_candle_responses and (
                failed == 0 or (discovered and empty_candle_responses and failed == empty_candle_responses)
            )) else (),
            failed_dates=requested_days if (not stored and failed and failed != empty_candle_responses) else (),
        )


def derive_historical_option_chain(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Align candle facts without pretending to reconstruct an exchange snapshot."""
    columns = ("timestamp","strike","expiry","side","ltp","open","high","low","close","volume","oi","bid","ask","iv","greeks")
    if not records: return pd.DataFrame(columns=columns)
    rows=[]
    for item in records:
        if not all(key in item for key in ("timestamp","strike","expiry","side","open","high","low","close")): continue
        rows.append({key: item.get(key) for key in columns})
    if not rows: return pd.DataFrame(columns=columns)
    frame=pd.DataFrame(rows); frame["timestamp"]=pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame=frame.dropna(subset=["timestamp","strike","expiry","side"])
    return frame.sort_values(["timestamp","expiry","strike","side"]).drop_duplicates(["timestamp","expiry","strike","side"], keep="last").reset_index(drop=True)


def option_coverage(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    frame=derive_historical_option_chain(records)
    if frame.empty: return {"contracts":0,"ce_count":0,"pe_count":0,"candle_coverage":0.0,"oi_coverage":0.0,"volume_coverage":0.0,"bid_ask":"Historical bid/ask unavailable","iv":"Historical IV unavailable","greeks":"Historical Greeks unavailable","derived_chain":"UNAVAILABLE"}
    return {"contracts":int(frame[["expiry","strike","side"]].drop_duplicates().shape[0]), "ce_count":int((frame.side=="CE").sum()), "pe_count":int((frame.side=="PE").sum()),
        "candle_coverage":100.0, "oi_coverage":round(frame.oi.notna().mean()*100,2), "volume_coverage":round(frame.volume.notna().mean()*100,2),
        "bid_ask":"Historical bid/ask unavailable", "iv":"Historical IV unavailable", "greeks":"Historical Greeks unavailable", "derived_chain":"PARTIAL_OPTION_REPLAY"}
