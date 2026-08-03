"""Versioned decision-time fingerprints and a local historical intelligence index.

This module consumes persisted Market Lake records.  It never invokes analytical
engines, and outcome metadata is deliberately kept outside fingerprints.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
import hashlib
import json
import math
import sqlite3

from .market_lake import HistoricalIntelligenceRecord


QUALITY_FLAGS = frozenset({
    "TRADE_ID_UNAVAILABLE", "TRADE_ID_COLLISION", "FINGERPRINT_INCOMPLETE",
    "FINGERPRINT_VERSION_OUTDATED", "FEATURE_SOURCE_MISSING", "FEATURE_VALUE_INVALID",
    "INDEX_RECORD_INVALID", "INDEX_SCHEMA_MISMATCH", "INDEX_REBUILD_REQUIRED",
    "DUPLICATE_TRADE_ID", "STATISTICS_CACHE_STALE", "RELATIONSHIP_GRAPH_INCOMPLETE",
    "MARKET_LAKE_RECORD_MISSING", "OUTCOME_METADATA_UNAVAILABLE", "TRIGGER_METADATA_UNAVAILABLE",
})


@dataclass(frozen=True)
class HistoricalIndexSettings:
    historical_index_enabled: bool = True
    historical_index_path: Path = Path("data/market_lake/index/historical_intelligence.sqlite")
    historical_index_schema_version: str = "1"
    fingerprint_version: str = "fp-v1"
    semantic_token_registry_version: str = "semantic-v1"
    feature_registry_version: str = "features-v1"
    fingerprint_unknown_token_policy: str = "INCLUDE_UNKNOWN"
    trade_id_hash_algorithm: str = "sha256"
    trade_id_hash_length: int = 20
    index_batch_size: int = 250
    index_checkpoint_interval: int = 100
    index_query_default_limit: int = 100
    index_query_maximum_limit: int = 1000
    statistics_cache_enabled: bool = True
    statistics_cache_version: str = "statistics-v1"
    relationship_graph_enabled: bool = True
    relationship_minimum_overlap: int = 2
    relationship_maximum_neighbors: int = 20
    index_auto_update_on_live_capture: bool = False
    index_auto_update_on_historical_enrichment: bool = False


SEMANTIC_REGISTRY = (
    ("MS", "market_structure"), ("REGIME", "market_regime"), ("CYCLE", "market_cycle"),
    ("LOC", "market_location"), ("PV", "price_volume_state"), ("POS", "positioning_state"),
    ("OPTPOS", "options_positioning"), ("COMP", "compression_state"),
    ("RELEASE", "release_state"), ("MANIP", "manipulation_state"), ("TRAP", "trap_state"),
    ("INST", "institutional_bias"), ("CONF", "decision_confidence"),
    ("VALID", "validation_state"), ("RANK", "ranking_state"),
    ("REC", "recommendation"), ("TRIG", "trigger_summary"), ("DATA", "replay_completeness"),
)


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    source_field: str
    divisor: float
    minimum: float
    maximum: float
    missing_behavior: str = "NONE"
    introduced: str = "fp-v1"


FEATURE_REGISTRY = tuple(FeatureDefinition(*row) for row in (
    ("decision_confidence", "decision_confidence", 100, 0, 1),
    ("recommendation_confidence", "recommendation_confidence", 100, 0, 1),
    ("compression_score", "compression_score", 100, 0, 1),
    ("energy_stored", "energy_stored", 100, 0, 1),
    ("expansion_readiness", "expansion_readiness", 100, 0, 1),
    ("volume_strength", "volume_strength", 100, 0, 1),
    ("institutional_evidence_quality", "institutional_evidence_quality", 100, 0, 1),
    ("manipulation_confidence", "manipulation_confidence", 100, 0, 1),
    ("positioning_confidence", "positioning_confidence", 100, 0, 1),
    ("validation_score", "validation_score", 100, 0, 1),
    ("ranking_score", "ranking_score", 100, 0, 1),
    ("pcr", "pcr", 2, 0, 1), ("iv_percentile", "iv_percentile", 100, 0, 1),
    ("oi_intensity", "oi_intensity", 100, 0, 1),
    ("distance_from_support", "distance_from_support", 100, 0, 1),
    ("distance_from_resistance", "distance_from_resistance", 100, 0, 1),
    ("atr_ratio", "atr_ratio", 5, 0, 1), ("relative_volume", "relative_volume", 5, 0, 1),
    ("market_location_score", "market_location_score", 100, 0, 1),
    ("trigger_pass_ratio", "trigger_pass_ratio", 1, 0, 1),
    ("blocker_count", "blocker_count", 10, 0, 1),
    ("missing_confirmation_count", "missing_confirmation_count", 10, 0, 1),
))

# Ordered aliases are deliberately explicit: extraction never searches arbitrary
# keys and therefore cannot accidentally pull similarly named outcome fields.
FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "market_structure": ("market_structure.state", "market_structure.structure", "market_structure"),
    "market_regime": ("market_regime.regime", "market_regime.state", "market_regime"),
    "market_cycle": ("market_cycle.cycle", "market_cycle.state", "market_cycle"),
    "market_location": ("market_location.location", "market_location.state", "market_location"),
    "price_volume_state": ("volume_structure.price_volume_state", "volume_structure.state", "price_volume_state"),
    "positioning_state": ("positioning_intelligence.state", "positioning_intelligence.positioning_state", "positioning_state"),
    "options_positioning": ("positioning_intelligence.options.state", "positioning_intelligence.options_positioning", "options_positioning"),
    "compression_state": ("compression_intelligence.state", "compression_intelligence.compression_state", "compression_state"),
    "release_state": ("compression_intelligence.release_state", "release_state"),
    "manipulation_state": ("manipulation_intelligence.state", "manipulation_intelligence.manipulation_state", "manipulation_state"),
    "trap_state": ("manipulation_intelligence.trap_state", "trap_state"),
    "institutional_bias": ("institutional_evidence.bias", "institutional_evidence.institutional_bias", "institutional_bias"),
    "validation_state": ("decision_confidence_validation.state", "decision_confidence_validation.validation_state", "validation_state"),
    "ranking_state": ("trade_opportunity_ranking.state", "trade_opportunity_ranking.ranking_state", "ranking_state"),
    "trigger_summary": ("trigger_review.summary", "trigger_summary"),
    "compression_score": ("compression_intelligence.compression_score", "compression_score"),
    "energy_stored": ("compression_intelligence.energy_stored", "energy_stored"),
    "expansion_readiness": ("compression_intelligence.expansion_readiness", "expansion_readiness"),
    "volume_strength": ("volume_structure.volume_strength", "volume_structure.strength", "volume_strength"),
    "institutional_evidence_quality": ("institutional_evidence.quality", "institutional_evidence.confidence", "institutional_evidence_quality"),
    "manipulation_confidence": ("manipulation_intelligence.confidence", "manipulation_confidence"),
    "positioning_confidence": ("positioning_intelligence.confidence", "positioning_confidence"),
    "validation_score": ("decision_confidence_validation.score", "validation_score"),
    "ranking_score": ("trade_opportunity_ranking.score", "ranking_score"),
    "decision_confidence": ("decision_confidence.score", "decision_confidence.confidence", "decision_confidence"),
    "recommendation_confidence": ("recommendation.confidence", "recommendation_confidence"),
    "market_location_score": ("market_location.score", "market_location_score"),
    "trigger_pass_ratio": ("trigger_review.pass_ratio", "trigger_pass_ratio"),
}


def nested_value(values: Mapping[str, Any], path: str) -> Any:
    """Resolve one dotted path without fuzzy matching or outcome traversal."""
    current: Any = values
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def extract_field(values: Mapping[str, Any], field: str) -> Any:
    for path in FIELD_ALIASES.get(field, (field,)):
        value = nested_value(values, path)
        if value is not None and not isinstance(value, Mapping):
            return value
    return None


def _norm(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return "UNKNOWN"
    text = "_".join(str(value).strip().upper().split())
    return "".join(c for c in text if c.isalnum() or c == "_")[:64] or "UNKNOWN"


def canonical_trade_identity(record: HistoricalIntelligenceRecord) -> str:
    return "|".join((record.provider, record.instrument_key, record.underlying,
                          str(record.interval_minutes), record.analysis_timestamp.isoformat(),
                          record.engine_version, record.schema_version))


def make_trade_id(record: HistoricalIntelligenceRecord, settings: HistoricalIndexSettings = HistoricalIndexSettings(), *, digest_strategy=None) -> str:
    canonical = canonical_trade_identity(record)
    digest = (digest_strategy or (lambda data: hashlib.new(settings.trade_id_hash_algorithm, data).hexdigest()))(canonical.encode())
    readable = _norm(record.underlying)[:12]
    return f"HTR-{readable}-{record.analysis_timestamp:%Y%m%d-%H%M%S}-{record.interval_minutes}M-{digest[:settings.trade_id_hash_length].upper()}"


@dataclass(frozen=True)
class MarketFingerprint:
    trade_id: str; fingerprint_version: str; feature_registry_version: str
    semantic_token_registry_version: str; engine_version: str; schema_version: str
    semantic_tokens: tuple[str, ...]; semantic_key: str
    numeric_features: tuple[tuple[str, float | None], ...]
    available_feature_count: int; missing_feature_count: int
    recommendation: str; direction: str
    quality_flags: tuple[str, ...]; explanations: tuple[str, ...]


def build_fingerprint(record: HistoricalIntelligenceRecord, settings: HistoricalIndexSettings = HistoricalIndexSettings()) -> MarketFingerprint:
    source = dict(record.values)
    source.update({k: getattr(record, k) for k in (
        "recommendation", "decision_confidence", "recommendation_confidence", "positioning_state",
        "compression_state", "manipulation_state", "replay_completeness")})
    for field in FIELD_ALIASES:
        resolved = extract_field(record.values, field)
        if resolved is not None: source[field] = resolved
    source.setdefault("ranking_state", "ELIGIBLE" if record.ranking_eligibility else "INELIGIBLE")
    confidence = source.get("decision_confidence")
    source["decision_confidence"] = (f"{max(0, min(90, int(float(confidence)//10*10)))}_100"
                                      if confidence is not None and float(confidence) >= 90 else
                                      f"{max(0, int(float(confidence)//10*10))}_{min(100, max(10, int(float(confidence)//10*10)+9))}"
                                      if confidence is not None else None)
    tokens, flags = [], set()
    for prefix, field in SEMANTIC_REGISTRY:
        value = _norm(source.get(field))
        if value == "UNKNOWN": flags.add("FINGERPRINT_INCOMPLETE")
        if value != "UNKNOWN" or settings.fingerprint_unknown_token_policy == "INCLUDE_UNKNOWN":
            tokens.append(f"{prefix}={value}")
    numeric = []
    values = {feature.source_field: extract_field(record.values, feature.source_field) for feature in FEATURE_REGISTRY}
    if record.decision_confidence is not None: values["decision_confidence"]=record.decision_confidence
    if record.recommendation_confidence is not None: values["recommendation_confidence"]=record.recommendation_confidence
    values.update(blocker_count=len(record.blockers), missing_confirmation_count=len(record.missing_confirmations))
    for feature in FEATURE_REGISTRY:
        raw = values.get(feature.source_field)
        try:
            number = None if raw is None else float(raw) / feature.divisor
            if number is not None and not math.isfinite(number): raise ValueError
            number = None if number is None else max(feature.minimum, min(feature.maximum, number))
        except (TypeError, ValueError):
            number = None; flags.add("FEATURE_VALUE_INVALID")
        if number is None: flags.add("FEATURE_SOURCE_MISSING")
        numeric.append((feature.name, number))
    direction = {"BUY CE": "BULLISH", "BUY PE": "BEARISH"}.get(record.recommendation, "NEUTRAL")
    return MarketFingerprint(make_trade_id(record, settings), settings.fingerprint_version,
        settings.feature_registry_version, settings.semantic_token_registry_version, record.engine_version,
        record.schema_version, tuple(tokens), "|".join(tokens), tuple(numeric),
        sum(v is not None for _, v in numeric), sum(v is None for _, v in numeric),
        record.recommendation, direction, tuple(sorted(flags)),
        ("Decision-time fields only; outcomes are stored separately.",))


@dataclass(frozen=True)
class IndexedHistoricalIntelligence:
    trade_id: str; logical_identity: str; provider: str; instrument_key: str; underlying: str; interval_minutes: int
    trading_date: date; analysis_timestamp: datetime; engine_version: str; schema_version: str
    fingerprint_version: str; recommendation: str; recommended_side: str; market_bias: str
    positioning_state: str; compression_state: str; manipulation_state: str; validation_state: str
    ranking_state: str; replay_completeness: str; decision_confidence: float | None
    trigger_pass_ratio: float | None; semantic_key: str; semantic_tokens: tuple[str, ...]
    numeric_features: tuple[tuple[str, float | None], ...]; primary_success_reason: str | None = None
    primary_failure_reason: str | None = None; outcome_classification: str | None = None
    quality_flags: tuple[str, ...] = (); indexed_at: datetime = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class HistoricalIndexQuery:
    trade_ids: tuple[str, ...] = (); instrument_key: str | None = None
    start_date: date | None = None; end_date: date | None = None; recommendation: str | None = None
    minimum_confidence: float | None = None; maximum_confidence: float | None = None
    positioning_state: str | None = None; compression_state: str | None = None
    manipulation_state: str | None = None; validation_state: str | None = None
    ranking_state: str | None = None; outcome_classification: str | None = None
    replay_completeness: str | None = None; engine_version: str | None = None
    fingerprint_version: str | None = None; semantic_tokens_all: tuple[str, ...] = ()
    semantic_tokens_any: tuple[str, ...] = (); limit: int = 100; offset: int = 0
    order_by: str = "analysis_timestamp"; descending: bool = False


@dataclass(frozen=True)
class HistoricalIndexStatus:
    total_market_lake_records: int; total_indexed_records: int; current_fingerprint_records: int
    outdated_fingerprint_records: int; missing_index_records: int; duplicate_trade_ids: int
    invalid_records: int; engine_versions: tuple[str, ...]; fingerprint_versions: tuple[str, ...]
    last_indexed_at: datetime | None; last_validated_at: datetime | None
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


class HistoricalIntelligenceIndex(Protocol):
    def upsert(self, record: IndexedHistoricalIntelligence) -> None: ...
    def query(self, query: HistoricalIndexQuery) -> tuple[IndexedHistoricalIntelligence, ...]: ...
    def get_status(self, market_lake_records: Iterable[HistoricalIntelligenceRecord] = ()) -> HistoricalIndexStatus: ...
    def validate_index(self, market_lake_records: Iterable[HistoricalIntelligenceRecord] = ()) -> Mapping[str, Any]: ...


_COLUMNS = tuple(IndexedHistoricalIntelligence.__dataclass_fields__)
_JSON_COLUMNS = {"semantic_tokens", "numeric_features", "quality_flags"}
_DATE_COLUMNS = {"trading_date", "analysis_timestamp", "indexed_at"}


class SQLiteHistoricalIntelligenceIndex:
    ALLOWED_ORDER = frozenset({"analysis_timestamp", "trading_date", "decision_confidence", "recommendation", "trade_id", "indexed_at"})
    def __init__(self, settings: HistoricalIndexSettings = HistoricalIndexSettings()):
        self.settings = settings; settings.historical_index_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
    def _connect(self):
        connection = sqlite3.connect(self.settings.historical_index_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def integrity_diagnostics(self) -> Mapping[str, Any]:
        """Return safe, connection-scoped SQLite diagnostics for the UI."""
        with self._connect() as db:
            integrity = str(db.execute("PRAGMA integrity_check").fetchone()[0])
            schema = db.execute(
                "SELECT value FROM index_metadata WHERE key='schema_version'"
            ).fetchone()
        return {
            "path": str(self.settings.historical_index_path),
            "schema_version": schema[0] if schema else None,
            "integrity": integrity,
            "fingerprint_version": self.settings.fingerprint_version,
        }
    def _initialize(self):
        definitions = ",".join(f"{c} " + ("REAL" if c in {"decision_confidence", "trigger_pass_ratio"} else "INTEGER" if c == "interval_minutes" else "TEXT") for c in _COLUMNS)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            existing = db.execute("SELECT value FROM index_metadata WHERE key='schema_version'").fetchone()
            if existing and existing[0] != self.settings.historical_index_schema_version: raise RuntimeError("INDEX_SCHEMA_MISMATCH")
            db.execute("INSERT OR IGNORE INTO index_metadata VALUES ('schema_version', ?)", (self.settings.historical_index_schema_version,))
            db.execute(f"CREATE TABLE IF NOT EXISTS historical_intelligence_index ({definitions}, PRIMARY KEY(trade_id, fingerprint_version))")
            for col in ("instrument_key","trading_date","analysis_timestamp","recommendation","decision_confidence","positioning_state","compression_state","manipulation_state","engine_version","fingerprint_version","outcome_classification","replay_completeness","semantic_key"):
                db.execute(f"CREATE INDEX IF NOT EXISTS idx_hii_{col} ON historical_intelligence_index({col})")
            db.execute("CREATE TABLE IF NOT EXISTS statistics_cache (cache_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, generation INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS change_generation (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO change_generation VALUES(1,0)")
            db.execute("CREATE TABLE IF NOT EXISTS index_validation (id INTEGER PRIMARY KEY CHECK(id=1), validated_at TEXT NOT NULL)")
    def _values(self, record):
        out=[]
        for c in _COLUMNS:
            v=getattr(record,c)
            if c in _JSON_COLUMNS: v=json.dumps(v, separators=(",",":"))
            elif c in _DATE_COLUMNS: v=v.isoformat()
            out.append(v)
        return out
    def upsert(self, record): self.bulk_upsert((record,))
    def bulk_upsert(self, records):
        records=tuple(records)
        sql=f"INSERT INTO historical_intelligence_index ({','.join(_COLUMNS)}) VALUES ({','.join('?' for _ in _COLUMNS)}) ON CONFLICT(trade_id,fingerprint_version) DO UPDATE SET "+",".join(f"{c}=excluded.{c}" for c in _COLUMNS if c not in {"trade_id","fingerprint_version"})
        with self._connect() as db:
            identities={}
            for record in records:
                if record.trade_id in identities and identities[record.trade_id]!=record.logical_identity: raise ValueError("TRADE_ID_COLLISION")
                identities[record.trade_id]=record.logical_identity
                collision=db.execute("SELECT logical_identity FROM historical_intelligence_index WHERE trade_id=? AND logical_identity<>? LIMIT 1",(record.trade_id,record.logical_identity)).fetchone()
                if collision: raise ValueError("TRADE_ID_COLLISION")
            db.executemany(sql, (self._values(r) for r in records)); db.execute("UPDATE change_generation SET generation=generation+1 WHERE id=1")
    def _record(self,row):
        d=dict(row)
        for c in _JSON_COLUMNS: d[c]=tuple(tuple(x) if isinstance(x,list) else x for x in json.loads(d[c]))
        d["trading_date"]=date.fromisoformat(d["trading_date"])
        for c in ("analysis_timestamp","indexed_at"): d[c]=datetime.fromisoformat(d[c])
        return IndexedHistoricalIntelligence(**d)
    def get_by_trade_id(self, trade_id, fingerprint_version=None):
        sql="SELECT * FROM historical_intelligence_index WHERE trade_id=?"; args=[trade_id]
        if fingerprint_version: sql+=" AND fingerprint_version=?"; args.append(fingerprint_version)
        sql+=" ORDER BY fingerprint_version DESC LIMIT 1"
        with self._connect() as db: row=db.execute(sql,args).fetchone()
        return self._record(row) if row else None
    def query(self,q=HistoricalIndexQuery()):
        if q.order_by not in self.ALLOWED_ORDER: raise ValueError("invalid order_by")
        if q.limit < 1 or q.limit > self.settings.index_query_maximum_limit or q.offset < 0: raise ValueError("invalid pagination")
        clauses=[]; args=[]
        fields=("instrument_key","recommendation","positioning_state","compression_state","manipulation_state","validation_state","ranking_state","outcome_classification","replay_completeness","engine_version","fingerprint_version")
        for f in fields:
            if (v:=getattr(q,f)) is not None: clauses.append(f"{f}=?"); args.append(v)
        for f,op,v in (("trading_date",">=",q.start_date),("trading_date","<=",q.end_date),("decision_confidence",">=",q.minimum_confidence),("decision_confidence","<=",q.maximum_confidence)):
            if v is not None: clauses.append(f"{f}{op}?"); args.append(v.isoformat() if isinstance(v,date) else v)
        if q.trade_ids: clauses.append(f"trade_id IN ({','.join('?' for _ in q.trade_ids)})"); args.extend(q.trade_ids)
        def safe_token(token):
            parts = str(token).split("=", 1)
            return f"{_norm(parts[0])}={_norm(parts[1])}" if len(parts) == 2 else _norm(token)
        for token in q.semantic_tokens_all: clauses.append("semantic_tokens LIKE ?"); args.append(f'%"{safe_token(token)}"%')
        if q.semantic_tokens_any:
            clauses.append("("+" OR ".join("semantic_tokens LIKE ?" for _ in q.semantic_tokens_any)+")"); args.extend(f'%"{safe_token(t)}"%' for t in q.semantic_tokens_any)
        sql="SELECT * FROM historical_intelligence_index"+(" WHERE "+" AND ".join(clauses) if clauses else "")
        sql+=f" ORDER BY {q.order_by} {'DESC' if q.descending else 'ASC'}, trade_id ASC LIMIT ? OFFSET ?"; args.extend((q.limit,q.offset))
        with self._connect() as db: return tuple(self._record(r) for r in db.execute(sql,args))
    def list_versions(self):
        with self._connect() as db: return tuple(r[0] for r in db.execute("SELECT DISTINCT fingerprint_version FROM historical_intelligence_index ORDER BY 1"))
    def delete_version(self, version):
        with self._connect() as db: db.execute("DELETE FROM historical_intelligence_index WHERE fingerprint_version=?",(version,)); db.execute("UPDATE change_generation SET generation=generation+1 WHERE id=1")
    def count(self, query=HistoricalIndexQuery()):
        return sum(1 for _ in self.iter_query(query))
    def iter_query(self, query=HistoricalIndexQuery()):
        offset=0
        while True:
            page=self.query(replace(query,limit=self.settings.index_query_maximum_limit,offset=offset))
            yield from page
            if len(page)<self.settings.index_query_maximum_limit:return
            offset+=len(page)
    def validate_index(self, market_lake_records: Iterable[HistoricalIntelligenceRecord] = ()):
        flags=set(); explanations=[]; invalid=0; logical=set(); duplicate=0
        with self._connect() as db:
            rows=tuple(db.execute("SELECT * FROM historical_intelligence_index"))
        for row in rows:
            try:
                if not all(row[k] for k in ("trade_id","logical_identity","instrument_key","engine_version","fingerprint_version")): raise ValueError("missing identity")
                datetime.fromisoformat(row["analysis_timestamp"]); datetime.fromisoformat(row["indexed_at"])
                tokens=json.loads(row["semantic_tokens"]); features=json.loads(row["numeric_features"]); json.loads(row["quality_flags"])
                if not isinstance(tokens,list) or not isinstance(features,list) or any(not isinstance(x,list) or len(x)!=2 or not isinstance(x[0],str) or (x[1] is not None and not isinstance(x[1],(int,float))) for x in features): raise ValueError("invalid vectors")
                key=(row["logical_identity"],row["fingerprint_version"])
                if key in logical: duplicate+=1
                logical.add(key)
                if row["fingerprint_version"]!=self.settings.fingerprint_version:flags.add("FINGERPRINT_VERSION_OUTDATED")
            except (ValueError,TypeError,json.JSONDecodeError): invalid+=1; flags.add("INDEX_RECORD_INVALID")
        lake_ids={canonical_trade_identity(r) for r in market_lake_records}; indexed_ids={row["logical_identity"] for row in rows}
        if lake_ids and indexed_ids-lake_ids: flags.add("MARKET_LAKE_RECORD_MISSING")
        now=datetime.now(timezone.utc)
        with self._connect() as db: db.execute("INSERT OR REPLACE INTO index_validation VALUES(1,?)",(now.isoformat(),))
        explanations.append(f"Validated {len(rows)} indexed records without mutation.")
        return {"invalid_records":invalid,"duplicate_trade_ids":duplicate,"quality_flags":tuple(sorted(flags)),"explanations":tuple(explanations),"validated_at":now}
    def get_status(self, market_lake_records: Iterable[HistoricalIntelligenceRecord] = ()):
        lake=tuple(market_lake_records); validation=self.validate_index(lake)
        with self._connect() as db:
            total=db.execute("SELECT COUNT(*) FROM historical_intelligence_index").fetchone()[0]
            current=db.execute("SELECT COUNT(*) FROM historical_intelligence_index WHERE fingerprint_version=?",(self.settings.fingerprint_version,)).fetchone()[0]
            engines=tuple(r[0] for r in db.execute("SELECT DISTINCT engine_version FROM historical_intelligence_index ORDER BY 1"))
            versions=tuple(r[0] for r in db.execute("SELECT DISTINCT fingerprint_version FROM historical_intelligence_index ORDER BY 1"))
            stamp=db.execute("SELECT MAX(indexed_at) FROM historical_intelligence_index").fetchone()[0]
        lake_identities={canonical_trade_identity(r) for r in lake}
        with self._connect() as db: indexed_identities={r[0] for r in db.execute("SELECT logical_identity FROM historical_intelligence_index") if r[0]}
        flags=set(validation["quality_flags"])
        if lake_identities-indexed_identities:flags.add("MARKET_LAKE_RECORD_MISSING")
        return HistoricalIndexStatus(len(lake),total,current,total-current,len(lake_identities-indexed_identities),validation["duplicate_trade_ids"],validation["invalid_records"],engines,versions,datetime.fromisoformat(stamp) if stamp else None,validation["validated_at"],tuple(sorted(flags)),validation["explanations"])


def indexed_record(record: HistoricalIntelligenceRecord, settings=HistoricalIndexSettings(), **outcome) -> IndexedHistoricalIntelligence:
    fp=build_fingerprint(record,settings); values=record.values
    return IndexedHistoricalIntelligence(fp.trade_id,canonical_trade_identity(record),record.provider,record.instrument_key,record.underlying,
        record.interval_minutes,record.trading_date,record.analysis_timestamp,record.engine_version,
        record.schema_version,fp.fingerprint_version,record.recommendation,
        {"BUY CE":"CE","BUY PE":"PE"}.get(record.recommendation,"WAIT"),record.market_bias or "UNKNOWN",
        record.positioning_state or "UNKNOWN",record.compression_state or "UNKNOWN",record.manipulation_state or "UNKNOWN",
        _norm(values.get("validation_state")),"ELIGIBLE" if record.ranking_eligibility else "INELIGIBLE",
        record.replay_completeness,record.decision_confidence,values.get("trigger_pass_ratio"),fp.semantic_key,
        fp.semantic_tokens,fp.numeric_features,outcome.get("primary_success_reason"),outcome.get("primary_failure_reason"),
        outcome.get("outcome_classification"),tuple(sorted(set(record.quality_flags)|set(fp.quality_flags))),datetime.now(timezone.utc))


@dataclass(frozen=True)
class IndexBuildResult:
    completed: int=0; skipped: int=0; failed: int=0; duplicate_trade_ids: int=0; checkpoint: str|None=None
    quality_flags: tuple[str,...]=()


class HistoricalIntelligenceIndexService:
    def __init__(self,index,settings=HistoricalIndexSettings(),checkpoint_path=None): self.index=index; self.settings=settings; self.checkpoint_path=Path(checkpoint_path) if checkpoint_path else settings.historical_index_path.with_suffix(".checkpoint.json")
    def build(self, records: Iterable[HistoricalIntelligenceRecord], *, rebuild_outdated=False, full_rebuild=False, resume=False):
        completed=skipped=failed=duplicates=0; seen=set(); batch=[]; checkpoint=None; flags=set(); resume_after=None
        if resume and self.checkpoint_path.exists():
            try: resume_after=json.loads(self.checkpoint_path.read_text()).get("last_trade_id")
            except (OSError,json.JSONDecodeError): resume_after=None
        resuming=bool(resume_after)
        for record in records:
            try:
                item=indexed_record(record,self.settings)
                if resuming:
                    skipped+=1
                    if item.trade_id==resume_after:resuming=False
                    continue
                if item.trade_id in seen: duplicates+=1; continue
                seen.add(item.trade_id); current=self.index.get_by_trade_id(item.trade_id,item.fingerprint_version)
                if current and not full_rebuild: skipped+=1; continue
                if self.index.get_by_trade_id(item.trade_id) and not rebuild_outdated and not full_rebuild: skipped+=1; continue
                batch.append(item); completed+=1; checkpoint=item.trade_id
                if len(batch)>=self.settings.index_batch_size:
                    try:self.index.bulk_upsert(batch)
                    except ValueError as error:
                        failed+=len(batch); completed-=len(batch)
                        if "TRADE_ID_COLLISION" in str(error):flags.add("TRADE_ID_COLLISION")
                    batch=[]
                if completed % self.settings.index_checkpoint_interval == 0: self._checkpoint(checkpoint)
            except (TypeError,ValueError,AttributeError) as error:
                failed+=1
                if "TRADE_ID_COLLISION" in str(error):flags.add("TRADE_ID_COLLISION")
        if batch:
            try:self.index.bulk_upsert(batch)
            except ValueError as error:
                failed+=len(batch); completed-=len(batch)
                if "TRADE_ID_COLLISION" in str(error):flags.add("TRADE_ID_COLLISION")
        if checkpoint:self._checkpoint(checkpoint)
        return IndexBuildResult(completed,skipped,failed,duplicates,checkpoint,tuple(sorted(flags)))
    def _checkpoint(self,trade_id):
        self.checkpoint_path.parent.mkdir(parents=True,exist_ok=True); self.checkpoint_path.write_text(json.dumps({"last_trade_id":trade_id},sort_keys=True))
    def refresh_outcome_metadata(self, trade_id, fingerprint_version, **metadata):
        old=self.index.get_by_trade_id(trade_id,fingerprint_version)
        if old:self.index.upsert(replace(old,primary_success_reason=metadata.get("primary_success_reason"),primary_failure_reason=metadata.get("primary_failure_reason"),outcome_classification=metadata.get("outcome_classification"),indexed_at=datetime.now(timezone.utc)))


class HistoricalIndexAutoUpdater:
    """Failure-isolated hooks for persistence services; disabled is a no-op."""
    def __init__(self, service: HistoricalIntelligenceIndexService, *, live_enabled=None, enrichment_enabled=None):
        self.service=service
        configured=getattr(service,"settings",HistoricalIndexSettings())
        self.live_enabled=configured.index_auto_update_on_live_capture if live_enabled is None else live_enabled
        self.enrichment_enabled=configured.index_auto_update_on_historical_enrichment if enrichment_enabled is None else enrichment_enabled
        self.diagnostics=[]
    def on_live_record(self, record): return self._build(record) if self.live_enabled else False
    def on_enriched_record(self, record): return self._build(record) if self.enrichment_enabled else False
    def _build(self, record):
        try:
            result=self.service.build((record,)); return bool(result.completed or result.skipped)
        except Exception:
            self.diagnostics.append("Historical intelligence auto-index failed."); return False
    def on_outcome(self, trade_id, fingerprint_version, **metadata):
        if not self.enrichment_enabled:return False
        try:self.service.refresh_outcome_metadata(trade_id,fingerprint_version,**metadata);return True
        except Exception:self.diagnostics.append("Historical outcome index refresh failed.");return False


class HistoricalStatisticsCache:
    def __init__(self,index): self.index=index
    def compute(self, query=HistoricalIndexQuery(), *, cache_identity="all"):
        records=tuple(self.index.iter_query(query)); confidences=sorted(r.decision_confidence for r in records if r.decision_confidence is not None)
        def counts(attr):
            out={}
            for r in records:
                key = getattr(r, attr) or "UNKNOWN"
                out[key] = out.get(key, 0) + 1
            return dict(sorted(out.items()))
        median=None if not confidences else (confidences[len(confidences)//2] if len(confidences)%2 else sum(confidences[len(confidences)//2-1:len(confidences)//2+1])/2)
        payload={"matching_record_count":len(records),"processed_record_count":len(records),"complete":True,"quality_flags":[],"recommendation_counts":counts("recommendation"),"positioning_counts":counts("positioning_state"),"compression_counts":counts("compression_state"),"manipulation_counts":counts("manipulation_state"),"outcome_classification_counts":counts("outcome_classification"),"ranking_state_distribution":counts("ranking_state"),"replay_completeness_distribution":counts("replay_completeness"),"engine_version_distribution":counts("engine_version"),"confidence_average":sum(confidences)/len(confidences) if confidences else None,"confidence_median":median}
        with self.index._connect() as db:
            generation=db.execute("SELECT generation FROM change_generation WHERE id=1").fetchone()[0]; key=hashlib.sha256((cache_identity+self.index.settings.statistics_cache_version).encode()).hexdigest(); db.execute("INSERT OR REPLACE INTO statistics_cache VALUES(?,?,?)",(key,json.dumps(payload,sort_keys=True),generation))
        return payload
    def get(self,cache_identity="all"):
        key=hashlib.sha256((cache_identity+self.index.settings.statistics_cache_version).encode()).hexdigest()
        with self.index._connect() as db: row=db.execute("SELECT payload_json,generation,(SELECT generation FROM change_generation WHERE id=1) FROM statistics_cache WHERE cache_key=?",(key,)).fetchone()
        return None if not row or row[1]!=row[2] else json.loads(row[0])


@dataclass(frozen=True)
class TradeRelationship:
    source_trade_id: str; target_trade_id: str; relationship_type: str
    shared_token_count: int; differing_token_count: int; preliminary_score: float
    fingerprint_version: str; explanations: tuple[str,...]

OPPOSITE_RULES=frozenset({frozenset(x) for x in (("REC=BUY_CE","REC=BUY_PE"),("MS=BULLISH","MS=BEARISH"),("POS=LONG_BUILDUP","POS=SHORT_BUILDUP"),("OPTPOS=PUT_WRITING","OPTPOS=CALL_WRITING"),("MANIP=FALSE_BREAKOUT","MANIP=FALSE_BREAKDOWN"),("TRAP=BULL_TRAP","TRAP=BEAR_TRAP"))})

def build_relationships(records: Sequence[IndexedHistoricalIntelligence], settings=HistoricalIndexSettings()):
    directed={r.trade_id:[] for r in records}; ordered=sorted(records,key=lambda x:x.trade_id)
    for i,a in enumerate(ordered):
        for b in ordered[i+1:]:
            if a.fingerprint_version!=b.fingerprint_version:continue
            left,right=set(a.semantic_tokens),set(b.semantic_tokens); shared=len(left&right)
            if shared<settings.relationship_minimum_overlap:continue
            score=max(0.0,min(1.0,shared/len(left|right))) if left|right else 0.0
            opposite=any(rule<=left|right and bool(rule&left) and bool(rule&right) for rule in OPPOSITE_RULES)
            kind="OPPOSITE_DIRECTION" if opposite else "SEMANTIC_NEIGHBOR"
            if not opposite and a.outcome_classification!=b.outcome_classification and score==1:kind="SAME_SETUP_DIFFERENT_OUTCOME"
            elif not opposite and a.outcome_classification and a.outcome_classification==b.outcome_classification and score<1:kind="SAME_OUTCOME_DIFFERENT_SETUP"
            explanation=(f"{shared} decision-state tokens shared.",)
            directed[a.trade_id].append(TradeRelationship(a.trade_id,b.trade_id,kind,shared,len(left^right),score,a.fingerprint_version,explanation))
            directed[b.trade_id].append(TradeRelationship(b.trade_id,a.trade_id,kind,shared,len(left^right),score,a.fingerprint_version,explanation))
    output=[]
    for trade_id in sorted(directed): output.extend(sorted(directed[trade_id],key=lambda x:(-x.preliminary_score,x.target_trade_id))[:settings.relationship_maximum_neighbors])
    return tuple(output)


def get_neighbors(relationships: Sequence[TradeRelationship], trade_id: str, *, limit: int | None = None):
    neighbors=sorted((edge for edge in relationships if edge.source_trade_id==trade_id),key=lambda x:(-x.preliminary_score,x.target_trade_id))
    return tuple(neighbors if limit is None else neighbors[:max(0,limit)])
