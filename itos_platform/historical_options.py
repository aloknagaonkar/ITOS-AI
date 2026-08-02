"""Official expired-instrument candle adapter and derived-chain projection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd

from .historical_sync import HistoricalMalformedResponseError, HistoricalProviderError, normalize_historical_candles
from .market_lake import LocalHistoricalMarketLake


class ExpiredOptionClient(Protocol):
    def get_expired_option_expiries(self, instrument_key: str) -> Sequence[str]: ...
    def get_expired_option_contracts(self, instrument_key: str, expiry_date: str) -> Sequence[Mapping[str, Any]]: ...
    def get_expired_historical_candles(self, expired_instrument_key: str, from_date: str, to_date: str, *, interval: int) -> pd.DataFrame: ...


@dataclass(frozen=True)
class HistoricalOptionDownloadResult:
    expiries_discovered: int; contracts_discovered: int; contracts_stored: int
    failed_contracts: int; status: str; explanations: tuple[str, ...] = ()
    ce_count: int = 0; pe_count: int = 0
    completed_dates: tuple[date, ...] = (); partial_dates: tuple[date, ...] = ()
    failed_dates: tuple[date, ...] = (); oi_coverage: float = 0.0; volume_coverage: float = 0.0


class HistoricalOptionDownloadService:
    """Explicit, read-only provider workflow; construction never makes a request."""
    def __init__(self, client: ExpiredOptionClient, lake: LocalHistoricalMarketLake, *, provider: str = "upstox"):
        self.client, self.lake, self.provider = client, lake, provider

    def discover_expiries(self, instrument_key: str) -> tuple[str, ...]:
        try:
            return tuple(str(value) for value in self.client.get_expired_option_expiries(instrument_key))
        except Exception:
            raise HistoricalProviderError("Upstox expired-option provider unavailable.") from None

    def download(self, instrument_key: str, start_date: date, end_date: date, *, expiry: str | None = None) -> HistoricalOptionDownloadResult:
        if start_date > end_date: raise ValueError("start_date must be on or before end_date")
        expiries = self.discover_expiries(instrument_key)
        if expiry is not None:
            if expiry not in expiries: raise ValueError("Selected expiry was not discovered for this instrument.")
            expiries = (expiry,)
        discovered = stored = failed = ce = pe = oi_present = volume_present = observations = 0
        completed_days: set[date] = set(); partial_days: set[date] = set(); failed_days: set[date] = set()
        for expiry_text in expiries:
            try: expiry = date.fromisoformat(str(expiry_text)); contracts = tuple(self.client.get_expired_option_contracts(instrument_key, expiry_text))
            except (ValueError, TypeError): continue
            except Exception: failed += 1; continue
            for contract in contracts:
                discovered += 1
                key = contract.get("expired_instrument_key") or contract.get("instrument_key")
                side = str(contract.get("instrument_type") or contract.get("option_type") or "").upper()
                strike = contract.get("strike_price")
                if not key or side not in {"CE", "PE"} or strike is None: failed += 1; continue
                try:
                    candles = normalize_historical_candles(self.client.get_expired_historical_candles(str(key), start_date.isoformat(), end_date.isoformat(), interval=1))
                    for day, frame in candles.groupby(candles["timestamp"].dt.date):
                        records = [{"timestamp": row.timestamp.isoformat(), "expiry": expiry.isoformat(), "strike": strike,
                            "side": side, "open": row.open, "high": row.high, "low": row.low, "close": row.close,
                            "ltp": row.close, "volume": row.volume if pd.notna(row.volume) else None,
                            "oi": row.open_interest if pd.notna(row.open_interest) else None,
                            "bid": None, "ask": None, "iv": None, "greeks": None,
                            "replay_completeness": "PARTIAL_OPTION_REPLAY"} for row in frame.itertuples()]
                        self.lake.store_option_snapshots(self.provider, instrument_key, expiry, day, frame.iloc[-1]["timestamp"].to_pydatetime(), records)
                        partial_days.add(day)
                        observations += len(records)
                        oi_present += sum(item["oi"] is not None for item in records)
                        volume_present += sum(item["volume"] is not None for item in records)
                    stored += 1
                    ce += side == "CE"; pe += side == "PE"
                except (HistoricalMalformedResponseError, Exception):
                    failed += 1; failed_days.update(date.fromordinal(value) for value in range(start_date.toordinal(), end_date.toordinal()+1))
        status = "PARTIAL_OPTION_REPLAY" if stored else "UNAVAILABLE"
        return HistoricalOptionDownloadResult(len(expiries), discovered, stored, failed, status,
            ("Expired candles do not provide historical bid/ask, IV, or Greeks.",), ce, pe,
            tuple(sorted(completed_days)), tuple(sorted(partial_days)), tuple(sorted(failed_days)),
            round(100*oi_present/observations, 2) if observations else 0.0,
            round(100*volume_present/observations, 2) if observations else 0.0)


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
