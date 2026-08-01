"""Typed, decision-neutral institutional option-chain evidence."""
from __future__ import annotations
from dataclasses import dataclass, fields, replace
from typing import Any
import numpy as np
import pandas as pd
from .decision_context import DecisionContext, MarketSnapshot

@dataclass(frozen=True)
class InstitutionalMetricsSettings:
    atm_window: int = 1
    weighted_pcr_oi_weight: float = .5
    weighted_pcr_change_weight: float = .25
    weighted_pcr_volume_weight: float = .25
    good_spread_ratio: float = .02
    poor_spread_ratio: float = .10
    thin_market_volume: float = 1000.
    liquid_market_volume: float = 10000.
    minimum_history_length: int = 3
    velocity_interval_seconds: float = 60.
    iv_percentile_lookback: int = 20
    greek_weighting: str = "oi"

@dataclass(frozen=True)
class OIMetrics:
    call_oi: float=0.; put_oi: float=0.; call_oi_change: float=0.; put_oi_change: float=0.
    call_oi_velocity: float|None=None; put_oi_velocity: float|None=None
    call_oi_acceleration: float|None=None; put_oi_acceleration: float|None=None
    atm_call_oi: float=0.; atm_put_oi: float=0.
@dataclass(frozen=True)
class PCRMetrics:
    oi_pcr: float|None=None; change_oi_pcr: float|None=None
    volume_pcr: float|None=None; weighted_pcr: float|None=None
@dataclass(frozen=True)
class VolatilityMetrics:
    call_iv: float|None=None; put_iv: float|None=None; atm_iv: float|None=None
    iv_skew: float|None=None; iv_percentile: float|None=None
@dataclass(frozen=True)
class GreeksMetrics:
    call_delta: float|None=None; put_delta: float|None=None; gamma: float|None=None
    theta: float|None=None; vega: float|None=None
    call_gamma_exposure: float|None=None; put_gamma_exposure: float|None=None
    net_gamma_exposure: float|None=None
@dataclass(frozen=True)
class LiquidityMetrics:
    call_volume: float=0.; put_volume: float=0.; total_volume: float=0.
    bid_ask_quality: float|None=None; liquidity_score: float=0.; thin_market: bool=True
@dataclass(frozen=True)
class PositioningMetrics:
    call_writing_score: float=0.; put_writing_score: float=0.
    long_buildup_score: float=0.; short_buildup_score: float=0.
    long_unwinding_score: float=0.; short_covering_score: float=0.
    dominant_state: str="unavailable"; direction: str="neutral"
@dataclass(frozen=True)
class InstitutionalMetrics:
    oi: OIMetrics; pcr: PCRMetrics; volatility: VolatilityMetrics
    greeks: GreeksMetrics; liquidity: LiquidityMetrics; positioning: PositioningMetrics
    max_pain: float|None=None; futures_premium: float|None=None
    quality_flags: tuple[str,...]=(); explanations: tuple[str,...]=()
    def preview(self)->dict[str,Any]:
        return {"oi_pcr":self.pcr.oi_pcr,"change_oi_pcr":self.pcr.change_oi_pcr,
                "max_pain":self.max_pain,"atm_iv":self.volatility.atm_iv,
                "iv_skew":self.volatility.iv_skew,"liquidity_score":self.liquidity.liquidity_score,
                "dominant_positioning_state":self.positioning.dominant_state,
                "quality_flags":self.quality_flags}

class OptionChainSchemaAdapter:
    """Central alias resolution and numeric coercion boundary."""
    ALIASES={
      "strike":("strike","strike_price","strikePrice"),
      "call_oi":("call_oi","ce_oi","CE_OI"),"put_oi":("put_oi","pe_oi","PE_OI"),
      "call_oi_change":("call_oi_change","ce_oi_change","call_change_oi"),
      "put_oi_change":("put_oi_change","pe_oi_change","put_change_oi"),
      "call_volume":("call_volume","ce_volume"),"put_volume":("put_volume","pe_volume"),
      "call_iv":("call_iv","ce_iv"),"put_iv":("put_iv","pe_iv"),
      "call_delta":("call_delta","ce_delta"),"put_delta":("put_delta","pe_delta"),
      "call_gamma":("call_gamma","ce_gamma"),"put_gamma":("put_gamma","pe_gamma"),
      "call_theta":("call_theta","ce_theta"),"put_theta":("put_theta","pe_theta"),
      "call_vega":("call_vega","ce_vega"),"put_vega":("put_vega","pe_vega"),
      "call_ltp":("call_ltp","ce_ltp"),"put_ltp":("put_ltp","pe_ltp"),
      "call_bid":("call_bid","ce_bid"),"call_ask":("call_ask","ce_ask"),
      "put_bid":("put_bid","pe_bid"),"put_ask":("put_ask","pe_ask"),
      "call_price_change":("call_price_change","ce_price_change"),
      "put_price_change":("put_price_change","pe_price_change")}
    def normalize(self,chain:Any)->tuple[pd.DataFrame,tuple[str,...]]:
        if not isinstance(chain,pd.DataFrame) or chain.empty:return pd.DataFrame(),("empty_option_chain",)
        out=pd.DataFrame(index=chain.index); flags=[]
        for canonical,aliases in self.ALIASES.items():
            source=next((x for x in aliases if x in chain),None)
            if source is None:flags.append("missing_"+canonical);continue
            out[canonical]=pd.to_numeric(chain[source],errors="coerce")
            if out[canonical].isna().any():flags.append("malformed_"+canonical)
        return out,tuple(flags)

class InstitutionalMetricsEngine:
    """Compute evidence once without recommendations, persistence, or UI access."""
    def __init__(self,settings:InstitutionalMetricsSettings|None=None):
        self.settings=settings or InstitutionalMetricsSettings();self.adapter=OptionChainSchemaAdapter()
    def analyze(self,source:DecisionContext|MarketSnapshot)->InstitutionalMetrics:
        context=source if isinstance(source,DecisionContext) else None
        snapshot=context.market_snapshot if context else source
        cfg=self._settings(context); chain,found=self.adapter.normalize(snapshot.option_result.get("chain"));flags=list(found)
        if chain.empty:return self._empty(flags)
        total=lambda c:float(chain[c].fillna(0).sum()) if c in chain else 0.
        co,po,cc,pc,cv,pv=map(total,("call_oi","put_oi","call_oi_change","put_oi_change","call_volume","put_volume"))
        atm=self._atm(chain,snapshot,cfg.atm_window); motion=self._motion(context.decision_history if context else None,cfg,flags)
        oi=OIMetrics(co,po,cc,pc,*motion,self._total(atm,"call_oi"),self._total(atm,"put_oi"))
        ratios=(self._ratio(po,co),self._ratio(pc,cc),self._ratio(pv,cv))
        if any(x is None for x in ratios):flags.append("pcr_denominator_unavailable")
        weights=(cfg.weighted_pcr_oi_weight,cfg.weighted_pcr_change_weight,cfg.weighted_pcr_volume_weight)
        available=[(v,w) for v,w in zip(ratios,weights) if v is not None and w>0]
        weighted=sum(v*w for v,w in available)/sum(w for _,w in available) if available else None
        summary=snapshot.option_result.get("summary") or {}
        return InstitutionalMetrics(oi,PCRMetrics(*ratios,weighted),self._volatility(chain,atm,context.decision_history if context else None,cfg,flags),
          self._greeks(chain,cfg,flags),self._liquidity(chain,cv,pv,cfg,flags),self._positioning(chain,flags),
          self._max_pain(chain,flags),self._number(summary.get("futures_premium")),tuple(dict.fromkeys(flags)),
          ("Observational only; does not influence Sprint 9 decisions.",))
    def _settings(self,c):
        values=c.runtime_configuration.get("institutional_metrics",{}) if c else {}; allowed={x.name for x in fields(InstitutionalMetricsSettings)}
        return replace(self.settings,**{k:v for k,v in values.items() if k in allowed})
    @staticmethod
    def _number(v):
        try:n=float(v);return n if np.isfinite(n) else None
        except (TypeError,ValueError):return None
    @staticmethod
    def _ratio(n,d):return n/d if d else None
    @staticmethod
    def _total(frame,col):return float(frame[col].fillna(0).sum()) if col in frame else 0.
    def _atm(self,chain,snapshot,window):
        if "strike" not in chain or chain.strike.dropna().empty:return chain.iloc[:0]
        summary=snapshot.option_result.get("summary") or {};spot=self._number(summary.get("spot")) or self._number(summary.get("atm"))
        pos=int(np.nanargmin(abs(chain.strike.to_numpy()-spot))) if spot is not None else len(chain)//2
        return chain.iloc[max(0,pos-window):pos+window+1]
    def _motion(self,history,cfg,flags):
        required=["timestamp","call_oi","put_oi"]
        if not isinstance(history,pd.DataFrame) or not set(required).issubset(history) or len(history)<cfg.minimum_history_length:
            flags.append("insufficient_oi_history");return None,None,None,None
        f=history[required].copy();f.timestamp=pd.to_datetime(f.timestamp,errors="coerce",utc=True)
        for c in required[1:]:f[c]=pd.to_numeric(f[c],errors="coerce")
        f=f.dropna().sort_values("timestamp")
        if len(f)<cfg.minimum_history_length:flags.append("insufficient_oi_history");return None,None,None,None
        d1=(f.timestamp.iloc[-1]-f.timestamp.iloc[-2]).total_seconds();d0=(f.timestamp.iloc[-2]-f.timestamp.iloc[-3]).total_seconds()
        if min(d0,d1)<=0:flags.append("invalid_history_timestamps");return None,None,None,None
        vel=[];acc=[]
        for c in required[1:]:
            v1=(f[c].iloc[-1]-f[c].iloc[-2])/d1*cfg.velocity_interval_seconds;v0=(f[c].iloc[-2]-f[c].iloc[-3])/d0*cfg.velocity_interval_seconds
            vel.append(float(v1));acc.append(float((v1-v0)/d1*cfg.velocity_interval_seconds))
        return vel[0],vel[1],acc[0],acc[1]
    def _volatility(self,chain,atm,history,cfg,flags):
        avg=lambda f,c:float(f[c].dropna().mean()) if c in f and not f[c].dropna().empty else None
        ci,pi=avg(chain,"call_iv"),avg(chain,"put_iv"); vals=[v for v in (avg(atm,"call_iv"),avg(atm,"put_iv")) if v is not None]
        ai=float(np.mean(vals)) if vals else None; percentile=None
        if isinstance(history,pd.DataFrame) and "atm_iv" in history:
            sample=pd.to_numeric(history.atm_iv,errors="coerce").dropna().tail(cfg.iv_percentile_lookback)
            if ai is not None and len(sample)>=cfg.minimum_history_length:percentile=float((sample<=ai).mean()*100)
        if ci is None or pi is None:flags.append("incomplete_iv")
        if percentile is None:flags.append("insufficient_iv_history")
        return VolatilityMetrics(ci,pi,ai,pi-ci if pi is not None and ci is not None else None,percentile)
    @staticmethod
    def _weighted(chain,value,weight):
        if value not in chain or weight not in chain:return None
        f=chain[[value,weight]].dropna();den=f[weight].abs().sum()
        return float((f[value]*f[weight].abs()).sum()/den) if den else None
    def _greeks(self,c,cfg,flags):
        w="volume" if cfg.greek_weighting=="volume" else "oi";get=lambda side,g:self._weighted(c,f"{side}_{g}",f"{side}_{w}")
        cd,pd_,cg,pg,ct,pt,cv,pv=(get("call","delta"),get("put","delta"),get("call","gamma"),get("put","gamma"),get("call","theta"),get("put","theta"),get("call","vega"),get("put","vega"))
        merge=lambda a,b:(a+b)/2 if a is not None and b is not None else a if b is None else b
        cge=float((c.call_gamma.fillna(0)*c.call_oi.fillna(0)).sum()) if {"call_gamma","call_oi"}.issubset(c) else None
        pge=float((c.put_gamma.fillna(0)*c.put_oi.fillna(0)).sum()) if {"put_gamma","put_oi"}.issubset(c) else None
        if any(x is None for x in (cd,pd_,cg,pg,ct,pt,cv,pv)):flags.append("incomplete_greeks")
        return GreeksMetrics(cd,pd_,merge(cg,pg),merge(ct,pt),merge(cv,pv),cge,pge,cge-pge if cge is not None and pge is not None else None)
    def _liquidity(self,c,cv,pv,cfg,flags):
        quality=[]
        for side in ("call","put"):
            if {side+"_bid",side+"_ask"}.issubset(c):
                bid,ask=c[side+"_bid"],c[side+"_ask"];mid=(bid+ask)/2;spread=((ask-bid)/mid).where(mid>0)
                quality.extend((1-(spread-cfg.good_spread_ratio)/(cfg.poor_spread_ratio-cfg.good_spread_ratio)).clip(0,1).dropna())
        quote=float(np.mean(quality)*100) if quality else None
        if quote is None:flags.append("missing_bid_ask")
        total=cv+pv;volume=min(100.,total/cfg.liquid_market_volume*100) if cfg.liquid_market_volume>0 else 0.;score=volume if quote is None else (volume+quote)/2
        if "call_volume" not in c or "put_volume" not in c:score=0.;flags.append("incomplete_volume")
        return LiquidityMetrics(cv,pv,total,quote,float(np.clip(score,0,100)),total<cfg.thin_market_volume)
    def _positioning(self,c,flags):
        needed={"call_oi_change","put_oi_change","call_price_change","put_price_change"}
        if not needed.issubset(c):flags.append("insufficient_positioning_data");return PositioningMetrics()
        scores={x:0. for x in ("long_buildup","short_buildup","long_unwinding","short_covering")};cw=pw=0.
        for side in ("call","put"):
            for price,oi in zip(c[side+"_price_change"],c[side+"_oi_change"]):
                if pd.isna(price) or pd.isna(oi):continue
                state="long_buildup" if price>0 and oi>0 else "short_buildup" if price<0 and oi>0 else "short_covering" if price>0 and oi<0 else "long_unwinding" if price<0 and oi<0 else None
                if state:scores[state]+=abs(float(oi))
                if state=="short_buildup":
                    if side=="call":cw+=abs(float(oi))
                    else:pw+=abs(float(oi))
        dominant=max(scores,key=scores.get) if any(scores.values()) else "neutral"
        return PositioningMetrics(cw,pw,scores["long_buildup"],scores["short_buildup"],scores["long_unwinding"],scores["short_covering"],dominant,"neutral")
    @staticmethod
    def _max_pain(c,flags):
        if not {"strike","call_oi","put_oi"}.issubset(c):flags.append("max_pain_unavailable");return None
        f=c[["strike","call_oi","put_oi"]].dropna()
        if f.empty:flags.append("max_pain_unavailable");return None
        strikes=f.strike.to_numpy();calls=f.call_oi.to_numpy();puts=f.put_oi.to_numpy();p=[(np.maximum(s-strikes,0)*calls+np.maximum(strikes-s,0)*puts).sum() for s in strikes]
        return float(strikes[int(np.argmin(p))])
    @staticmethod
    def _empty(flags):
        return InstitutionalMetrics(OIMetrics(),PCRMetrics(),VolatilityMetrics(),GreeksMetrics(),LiquidityMetrics(),PositioningMetrics(),quality_flags=tuple(dict.fromkeys(flags)),explanations=("Option-chain unavailable; no direction inferred.",))
