from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    captured_minute TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    spot REAL NOT NULL,
    atm REAL NOT NULL,
    pcr_oi REAL NOT NULL,
    pcr_volume REAL NOT NULL,
    max_pain REAL NOT NULL,
    support REAL NOT NULL,
    resistance REAL NOT NULL,
    call_oi REAL NOT NULL,
    put_oi REAL NOT NULL,
    call_volume REAL NOT NULL,
    put_volume REAL NOT NULL,
    call_oi_change REAL NOT NULL,
    put_oi_change REAL NOT NULL,
    atm_iv REAL NOT NULL,
    iv_skew REAL NOT NULL,
    option_score REAL NOT NULL,
    price_score REAL NOT NULL,
    combined_score REAL NOT NULL,
    state TEXT NOT NULL,
    confidence REAL NOT NULL,
    UNIQUE(captured_minute, underlying, expiry)
);

CREATE TABLE IF NOT EXISTS strike_snapshots (
    snapshot_id INTEGER NOT NULL,
    strike REAL NOT NULL,
    call_ltp REAL NOT NULL,
    call_oi REAL NOT NULL,
    call_volume REAL NOT NULL,
    call_iv REAL NOT NULL,
    call_delta REAL NOT NULL,
    call_gamma REAL NOT NULL,
    call_theta REAL NOT NULL,
    call_vega REAL NOT NULL,
    put_ltp REAL NOT NULL,
    put_oi REAL NOT NULL,
    put_volume REAL NOT NULL,
    put_iv REAL NOT NULL,
    put_delta REAL NOT NULL,
    put_gamma REAL NOT NULL,
    put_theta REAL NOT NULL,
    put_vega REAL NOT NULL,
    PRIMARY KEY(snapshot_id, strike),
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trade_history (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    side TEXT NOT NULL,
    strike REAL NOT NULL,
    contract TEXT NOT NULL,
    instrument_key TEXT,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    target1 REAL NOT NULL,
    target2 REAL NOT NULL,
    signal_score REAL NOT NULL,
    confidence REAL NOT NULL,
    market_regime TEXT,
    trade_quality REAL,
    health_score REAL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    outcome TEXT,
    exit_price REAL,
    current_ltp REAL NOT NULL,
    max_ltp REAL NOT NULL,
    min_ltp REAL NOT NULL,
    pnl_points REAL,
    pnl_percent REAL,
    close_reason TEXT,
    last_updated TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS confidence_history (
    confidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    side TEXT NOT NULL,
    market_confidence REAL NOT NULL,
    direction_confidence REAL NOT NULL,
    trigger_confidence REAL NOT NULL,
    calibrated_confidence REAL NOT NULL,
    confidence_label TEXT NOT NULL,
    consensus_agreeing INTEGER NOT NULL,
    consensus_total INTEGER NOT NULL,
    lifecycle TEXT NOT NULL,
    UNIQUE(captured_at, underlying, expiry)
);

CREATE INDEX IF NOT EXISTS idx_confidence_history_market_time
ON confidence_history(underlying, expiry, captured_at);



CREATE TABLE IF NOT EXISTS phase_history (
    phase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    phase TEXT NOT NULL,
    phase_confidence REAL NOT NULL,
    vote TEXT NOT NULL,
    manipulation_score REAL NOT NULL,
    trade_allowed INTEGER NOT NULL,
    probabilities_json TEXT NOT NULL,
    UNIQUE(captured_at, underlying, expiry)
);

CREATE TABLE IF NOT EXISTS stability_history (
    stability_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    side TEXT NOT NULL,
    stability_score REAL NOT NULL,
    stability_label TEXT NOT NULL,
    trend TEXT NOT NULL,
    direction_changes INTEGER NOT NULL,
    confidence_std REAL NOT NULL,
    passed INTEGER NOT NULL,
    UNIQUE(captured_at, underlying, expiry)
);

CREATE INDEX IF NOT EXISTS idx_phase_history_market_time
ON phase_history(underlying, expiry, captured_at);

CREATE INDEX IF NOT EXISTS idx_stability_history_market_time
ON stability_history(underlying, expiry, captured_at);

CREATE INDEX IF NOT EXISTS idx_trade_history_market
ON trade_history(underlying, expiry, opened_at);

CREATE INDEX IF NOT EXISTS idx_trade_history_active
ON trade_history(status, underlying, expiry, side, strike);

CREATE INDEX IF NOT EXISTS idx_snapshots_market_time
ON snapshots(underlying, expiry, captured_at);

CREATE INDEX IF NOT EXISTS idx_strike_snapshots_strike
ON strike_snapshots(strike, snapshot_id);


CREATE TABLE IF NOT EXISTS decision_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    captured_minute TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    side TEXT NOT NULL,
    status TEXT NOT NULL,
    confirmed INTEGER NOT NULL,
    confidence REAL NOT NULL,
    trade_quality REAL NOT NULL,
    market_regime TEXT,
    smart_money_index REAL,
    market_energy REAL,
    opportunity_stage TEXT,
    historical_similarity REAL,
    historical_vote TEXT,
    playbook TEXT,
    playbook_score REAL,
    evidence_json TEXT NOT NULL,
    report TEXT,
    UNIQUE(captured_minute, underlying, expiry)
);

CREATE TABLE IF NOT EXISTS playbook_history (
    playbook_id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    underlying TEXT NOT NULL,
    expiry TEXT NOT NULL,
    playbook TEXT NOT NULL,
    score REAL NOT NULL,
    vote TEXT NOT NULL,
    status TEXT NOT NULL,
    rankings_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decision_audit_market_time
ON decision_audit(underlying, expiry, captured_at);

CREATE INDEX IF NOT EXISTS idx_playbook_history_market_time
ON playbook_history(underlying, expiry, captured_at);
"""


class SnapshotStore:
    def __init__(self, path: str | Path = "market_intelligence.db") -> None:
        self.path = Path(path)
        self.initialise()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialise(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            existing = {row["name"] for row in connection.execute("PRAGMA table_info(trade_history)").fetchall()}
            migrations = {
                "market_regime": "ALTER TABLE trade_history ADD COLUMN market_regime TEXT",
                "trade_quality": "ALTER TABLE trade_history ADD COLUMN trade_quality REAL",
                "health_score": "ALTER TABLE trade_history ADD COLUMN health_score REAL",
            }
            for column, statement in migrations.items():
                if column not in existing:
                    connection.execute(statement)

    def save_snapshot(
        self,
        underlying: str,
        expiry: str,
        option_result: dict[str, Any],
        intelligence: dict[str, Any],
        captured_at: datetime | None = None,
    ) -> tuple[int, bool]:
        now = captured_at or datetime.now().astimezone()
        captured_at_text = now.isoformat(timespec="seconds")
        captured_minute = now.replace(second=0, microsecond=0).isoformat(timespec="minutes")
        summary = option_result["summary"]
        chain = option_result["chain"]

        call_oi = float(chain["call_oi"].sum())
        put_oi = float(chain["put_oi"].sum())
        call_volume = float(chain["call_volume"].sum())
        put_volume = float(chain["put_volume"].sum())

        values = (
            captured_at_text,
            captured_minute,
            underlying,
            expiry,
            float(summary["spot"]),
            float(summary["atm"]),
            float(summary["pcr_oi"]),
            float(summary["pcr_volume"]),
            float(summary["max_pain"]),
            float(summary["support"]),
            float(summary["resistance"]),
            call_oi,
            put_oi,
            call_volume,
            put_volume,
            float(summary["call_oi_change"]),
            float(summary["put_oi_change"]),
            float(summary["atm_iv"]),
            float(summary["iv_skew"]),
            float(summary["score"]),
            float(intelligence["price"]["score"]),
            float(intelligence["score"]),
            str(intelligence["state"]),
            float(intelligence["confidence"]),
        )

        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT snapshot_id FROM snapshots
                WHERE captured_minute = ? AND underlying = ? AND expiry = ?
                """,
                (captured_minute, underlying, expiry),
            ).fetchone()
            created = existing is None
            if existing:
                snapshot_id = int(existing["snapshot_id"])
                connection.execute("DELETE FROM strike_snapshots WHERE snapshot_id = ?", (snapshot_id,))
                connection.execute("DELETE FROM snapshots WHERE snapshot_id = ?", (snapshot_id,))

            cursor = connection.execute(
                """
                INSERT INTO snapshots (
                    captured_at, captured_minute, underlying, expiry, spot, atm,
                    pcr_oi, pcr_volume, max_pain, support, resistance,
                    call_oi, put_oi, call_volume, put_volume,
                    call_oi_change, put_oi_change, atm_iv, iv_skew,
                    option_score, price_score, combined_score, state, confidence
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            snapshot_id = int(cursor.lastrowid)

            strike_rows = []
            for row in chain.itertuples(index=False):
                strike_rows.append(
                    (
                        snapshot_id,
                        float(row.strike),
                        float(row.call_ltp),
                        float(row.call_oi),
                        float(row.call_volume),
                        float(row.call_iv),
                        float(row.call_delta),
                        float(row.call_gamma),
                        float(row.call_theta),
                        float(row.call_vega),
                        float(row.put_ltp),
                        float(row.put_oi),
                        float(row.put_volume),
                        float(row.put_iv),
                        float(row.put_delta),
                        float(row.put_gamma),
                        float(row.put_theta),
                        float(row.put_vega),
                    )
                )
            connection.executemany(
                """
                INSERT INTO strike_snapshots (
                    snapshot_id, strike, call_ltp, call_oi, call_volume,
                    call_iv, call_delta, call_gamma, call_theta, call_vega,
                    put_ltp, put_oi, put_volume, put_iv, put_delta,
                    put_gamma, put_theta, put_vega
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                strike_rows,
            )
        return snapshot_id, created

    def get_history(self, underlying: str, expiry: str, hours: int = 8) -> pd.DataFrame:
        cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT * FROM snapshots
                WHERE underlying = ? AND expiry = ? AND captured_at >= ?
                ORDER BY captured_at
                """,
                connection,
                params=(underlying, expiry, cutoff),
                parse_dates=["captured_at"],
            )

    def get_strike_history(
        self, underlying: str, expiry: str, hours: int = 8
    ) -> pd.DataFrame:
        cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT
                    s.snapshot_id AS snapshot_id,
                    s.captured_at AS captured_at,
                    s.spot AS spot,
                    ss.strike,
                    ss.call_ltp, ss.call_oi, ss.call_volume,
                    ss.call_iv, ss.call_delta, ss.call_gamma, ss.call_theta, ss.call_vega,
                    ss.put_ltp, ss.put_oi, ss.put_volume,
                    ss.put_iv, ss.put_delta, ss.put_gamma, ss.put_theta, ss.put_vega
                FROM snapshots s
                JOIN strike_snapshots ss ON ss.snapshot_id = s.snapshot_id
                WHERE s.underlying = ? AND s.expiry = ? AND s.captured_at >= ?
                ORDER BY s.captured_at, ss.strike
                """,
                connection,
                params=(underlying, expiry, cutoff),
                parse_dates=["captured_at"],
            )

    def count_snapshots(self, underlying: str, expiry: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM snapshots WHERE underlying = ? AND expiry = ?",
                (underlying, expiry),
            ).fetchone()
            return int(row["count"] if row else 0)

    def sync_trade_history(
        self,
        underlying: str,
        expiry: str,
        recommendation: dict[str, Any],
        chain: pd.DataFrame,
        captured_at: datetime | None = None,
    ) -> dict[str, int]:
        """Open newly triggered candidates and close active trades at target or stop.

        A trade is marked SUCCESS when Target 1 is reached and FAILURE when the
        stop-loss is reached. Target 2 remains stored for analysis. Since the app
        refreshes periodically, outcomes are based on the latest observed option LTP.
        """
        now = captured_at or datetime.now().astimezone()
        now_text = now.isoformat(timespec="seconds")

        price_map: dict[tuple[str, float], float] = {}
        for row in chain.itertuples(index=False):
            strike = float(row.strike)
            price_map[("CE", strike)] = float(getattr(row, "call_ltp", 0.0) or 0.0)
            price_map[("PE", strike)] = float(getattr(row, "put_ltp", 0.0) or 0.0)

        opened = completed_success = completed_failure = 0
        with self.connect() as connection:
            active_rows = connection.execute(
                """
                SELECT * FROM trade_history
                WHERE underlying = ? AND expiry = ? AND status = 'ACTIVE'
                """,
                (underlying, expiry),
            ).fetchall()

            for trade in active_rows:
                side = str(trade["side"])
                strike = float(trade["strike"])
                ltp = float(price_map.get((side, strike), trade["current_ltp"]))
                if ltp <= 0:
                    continue
                max_ltp = max(float(trade["max_ltp"]), ltp)
                min_ltp = min(float(trade["min_ltp"]), ltp)
                status = "ACTIVE"
                outcome = None
                reason = None
                exit_price = None

                if ltp >= float(trade["target1"]):
                    status = "COMPLETED"
                    outcome = "SUCCESS"
                    reason = "Target 1 reached"
                    exit_price = ltp
                    completed_success += 1
                elif ltp <= float(trade["stop_loss"]):
                    status = "COMPLETED"
                    outcome = "FAILURE"
                    reason = "Stop-loss reached"
                    exit_price = ltp
                    completed_failure += 1

                pnl_points = (exit_price - float(trade["entry_price"])) if exit_price is not None else None
                pnl_percent = (pnl_points / float(trade["entry_price"]) * 100.0) if pnl_points is not None and float(trade["entry_price"]) else None
                connection.execute(
                    """
                    UPDATE trade_history
                    SET current_ltp = ?, max_ltp = ?, min_ltp = ?, status = ?,
                        outcome = ?, exit_price = ?, pnl_points = ?, pnl_percent = ?,
                        close_reason = ?, closed_at = CASE WHEN ? = 'COMPLETED' THEN ? ELSE closed_at END,
                        last_updated = ?
                    WHERE trade_id = ?
                    """,
                    (ltp, max_ltp, min_ltp, status, outcome, exit_price, pnl_points,
                     pnl_percent, reason, status, now_text, now_text, int(trade["trade_id"])),
                )

            for table_key in ("ce_top5", "pe_top5"):
                candidates = recommendation.get(table_key)
                if candidates is None or candidates.empty:
                    continue
                for row in candidates.itertuples(index=False):
                    if str(getattr(row, "trade_state", "WAITING")) != "TRIGGERED":
                        continue
                    side = str(getattr(row, "side"))
                    strike = float(getattr(row, "strike"))
                    already_active = connection.execute(
                        """
                        SELECT 1 FROM trade_history
                        WHERE underlying = ? AND expiry = ? AND side = ? AND strike = ?
                          AND status = 'ACTIVE'
                        LIMIT 1
                        """,
                        (underlying, expiry, side, strike),
                    ).fetchone()
                    if already_active:
                        continue
                    entry = float(getattr(row, "entry_trigger"))
                    current = float(price_map.get((side, strike), getattr(row, "premium", entry)))
                    if current <= 0:
                        current = entry
                    connection.execute(
                        """
                        INSERT INTO trade_history (
                            opened_at, underlying, expiry, side, strike, contract,
                            instrument_key, entry_price, stop_loss, target1, target2,
                            signal_score, confidence, market_regime, trade_quality, health_score,
                            status, current_ltp, max_ltp, min_ltp, last_updated
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?,?)
                        """,
                        (now_text, underlying, expiry, side, strike, f"{strike:.0f} {side}",
                         str(getattr(row, "instrument_key", "")), entry,
                         float(getattr(row, "stop_loss")), float(getattr(row, "target1")),
                         float(getattr(row, "target2")), float(getattr(row, "final_score")),
                         float(recommendation.get("confidence", 0.0)),
                         str(recommendation.get("regime", {}).get("name", "")),
                         float(recommendation.get("trade_quality", 0.0)),
                         float(recommendation.get("health_score", 0.0)),
                         current, current, current, now_text),
                    )
                    opened += 1

        return {
            "opened": opened,
            "completed_success": completed_success,
            "completed_failure": completed_failure,
        }

    def save_confidence_history(
        self, underlying: str, expiry: str, recommendation: dict[str, Any], captured_at: datetime | None = None
    ) -> None:
        now = captured_at or datetime.now().astimezone()
        detail = recommendation.get("confidence_detail", {})
        consensus = detail.get("consensus", {})
        lifecycle = "TRIGGERED" if recommendation.get("confirmed") else (
            "READY / WATCH" if recommendation.get("passed_conditions", 0) >= recommendation.get("total_conditions", 1) - 1 else "WAITING"
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO confidence_history (
                    captured_at, underlying, expiry, side, market_confidence,
                    direction_confidence, trigger_confidence, calibrated_confidence,
                    confidence_label, consensus_agreeing, consensus_total, lifecycle
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (now.isoformat(timespec="seconds"), underlying, expiry, str(recommendation.get("side", "")),
                 float(detail.get("market_confidence", 0)), float(detail.get("direction_confidence", 0)),
                 float(detail.get("trigger_confidence", 0)), float(recommendation.get("confidence", 0)),
                 str(detail.get("label", "")), int(consensus.get("agreeing", 0)),
                 int(consensus.get("total", 0)), lifecycle),
            )

    def get_confidence_history(self, underlying: str, expiry: str, hours: int = 8) -> pd.DataFrame:
        cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT captured_at, side, market_confidence, direction_confidence,
                       trigger_confidence, calibrated_confidence, confidence_label,
                       consensus_agreeing, consensus_total, lifecycle
                FROM confidence_history
                WHERE underlying = ? AND expiry = ? AND captured_at >= ?
                ORDER BY captured_at
                """, connection, params=(underlying, expiry, cutoff), parse_dates=["captured_at"]
            )

    def get_trade_history(
        self, underlying: str, expiry: str, limit: int = 200
    ) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT * FROM trade_history
                WHERE underlying = ? AND expiry = ?
                ORDER BY opened_at DESC
                LIMIT ?
                """,
                connection,
                params=(underlying, expiry, limit),
                parse_dates=["opened_at", "closed_at", "last_updated"],
            )

    def trade_statistics(self, underlying: str, expiry: str) -> dict[str, float]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) AS active,
                    SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) AS success,
                    SUM(CASE WHEN outcome = 'FAILURE' THEN 1 ELSE 0 END) AS failure,
                    AVG(CASE WHEN status = 'COMPLETED' THEN pnl_percent END) AS avg_pnl_percent,
                    AVG(CASE WHEN outcome = 'SUCCESS' THEN pnl_percent END) AS avg_winner,
                    AVG(CASE WHEN outcome = 'FAILURE' THEN pnl_percent END) AS avg_loser,
                    SUM(CASE WHEN pnl_points > 0 THEN pnl_points ELSE 0 END) AS gross_profit,
                    ABS(SUM(CASE WHEN pnl_points < 0 THEN pnl_points ELSE 0 END)) AS gross_loss
                FROM trade_history
                WHERE underlying = ? AND expiry = ?
                """,
                (underlying, expiry),
            ).fetchone()
        total = int(row["total"] or 0)
        active = int(row["active"] or 0)
        success = int(row["success"] or 0)
        failure = int(row["failure"] or 0)
        completed = success + failure
        return {
            "total": total,
            "active": active,
            "success": success,
            "failure": failure,
            "completed": completed,
            "success_rate": (success / completed * 100.0) if completed else 0.0,
            "avg_pnl_percent": float(row["avg_pnl_percent"] or 0.0),
            "avg_winner": float(row["avg_winner"] or 0.0),
            "avg_loser": float(row["avg_loser"] or 0.0),
            "profit_factor": (float(row["gross_profit"] or 0.0) / float(row["gross_loss"])) if float(row["gross_loss"] or 0.0) else 0.0,
        }

    def save_phase_history(self, underlying: str, expiry: str, result: Any) -> None:
        metadata = getattr(result, "metadata", {})
        captured_at = getattr(result, "captured_at", datetime.now().astimezone().isoformat(timespec="seconds"))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO phase_history (
                    captured_at, underlying, expiry, phase, phase_confidence,
                    vote, manipulation_score, trade_allowed, probabilities_json
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (captured_at, underlying, expiry, str(metadata.get("phase", "Unknown")),
                 float(metadata.get("phase_confidence", 0.0)), str(getattr(result, "vote", "WAIT")),
                 float(metadata.get("manipulation_score", 0.0)), int(bool(metadata.get("trade_allowed", False))),
                 json.dumps(metadata.get("probabilities", {}), sort_keys=True)),
            )

    def get_phase_history(self, underlying: str, expiry: str, hours: int = 8) -> pd.DataFrame:
        cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT captured_at, phase, phase_confidence, vote, manipulation_score, trade_allowed
                FROM phase_history
                WHERE underlying = ? AND expiry = ? AND captured_at >= ?
                ORDER BY captured_at
                """, connection, params=(underlying, expiry, cutoff), parse_dates=["captured_at"]
            )

    def save_stability_history(self, underlying: str, expiry: str, side: str, result: Any) -> None:
        metadata = getattr(result, "metadata", {})
        captured_at = getattr(result, "captured_at", datetime.now().astimezone().isoformat(timespec="seconds"))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO stability_history (
                    captured_at, underlying, expiry, side, stability_score,
                    stability_label, trend, direction_changes, confidence_std, passed
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (captured_at, underlying, expiry, side, float(metadata.get("stability_score", 0.0)),
                 str(metadata.get("label", "Unknown")), str(metadata.get("trend", "Unknown")),
                 int(metadata.get("direction_changes", 0)), float(metadata.get("confidence_std", 0.0)),
                 int(bool(metadata.get("passed", False)))),
            )

    def get_stability_history(self, underlying: str, expiry: str, hours: int = 8) -> pd.DataFrame:
        cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT captured_at, side, stability_score, stability_label, trend,
                       direction_changes, confidence_std, passed
                FROM stability_history
                WHERE underlying = ? AND expiry = ? AND captured_at >= ?
                ORDER BY captured_at
                """, connection, params=(underlying, expiry, cutoff), parse_dates=["captured_at"]
            )


    def save_decision_audit(
        self, underlying: str, expiry: str, recommendation: dict[str, Any],
        regime_result: Any, smi_result: Any, energy_result: Any,
        opportunity_result: Any, similarity_result: Any, playbook_result: Any,
        report_result: Any, captured_at: datetime | None = None,
    ) -> None:
        now = captured_at or datetime.now().astimezone()
        minute = now.replace(second=0, microsecond=0).isoformat(timespec="minutes")
        regime = getattr(regime_result, "metadata", {}) or {}
        opportunity = getattr(opportunity_result, "metadata", {}) or {}
        similarity = getattr(similarity_result, "metadata", {}) or {}
        playbook = getattr(playbook_result, "metadata", {}) or {}
        primary = playbook.get("primary", {}) or {}
        report = getattr(report_result, "metadata", {}) or {}
        evidence = {
            "blockers": recommendation.get("blockers", []),
            "passed_conditions": recommendation.get("passed_conditions", 0),
            "total_conditions": recommendation.get("total_conditions", 0),
            "confidence_detail": recommendation.get("confidence_detail", {}),
            "regime": regime,
            "opportunity": opportunity,
            "similarity_top_match": similarity.get("top_match", {}),
            "playbook_rankings": playbook.get("rankings", []),
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO decision_audit (
                    captured_at, captured_minute, underlying, expiry, side, status,
                    confirmed, confidence, trade_quality, market_regime,
                    smart_money_index, market_energy, opportunity_stage,
                    historical_similarity, historical_vote, playbook, playbook_score,
                    evidence_json, report
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (now.isoformat(timespec="seconds"), minute, underlying, expiry,
                 str(recommendation.get("side", "WAIT")), str(recommendation.get("status", "WAIT")),
                 int(bool(recommendation.get("confirmed"))), float(recommendation.get("confidence", 0.0)),
                 float(recommendation.get("trade_quality", 0.0)), str(regime.get("regime", "Unknown")),
                 float(getattr(smi_result, "score", 0.0)), float(getattr(energy_result, "score", 0.0)),
                 str(opportunity.get("stage", "SCANNING")), float(getattr(similarity_result, "score", 0.0)),
                 str(getattr(similarity_result, "vote", "WAIT")), str(primary.get("Playbook", "Unknown")),
                 float(primary.get("Score", 0.0)), json.dumps(evidence, default=str, sort_keys=True),
                 str(report.get("report", ""))),
            )

    def get_decision_audit(self, underlying: str, expiry: str, limit: int = 250) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT audit_id, captured_at, side, status, confirmed, confidence,
                       trade_quality, market_regime, smart_money_index, market_energy,
                       opportunity_stage, historical_similarity, historical_vote,
                       playbook, playbook_score, report
                FROM decision_audit
                WHERE underlying = ? AND expiry = ?
                ORDER BY captured_at DESC
                LIMIT ?
                """, connection, params=(underlying, expiry, limit), parse_dates=["captured_at"]
            )

    def save_playbook_history(self, underlying: str, expiry: str, result: Any) -> None:
        metadata = getattr(result, "metadata", {}) or {}
        primary = metadata.get("primary", {}) or {}
        captured_at = getattr(result, "captured_at", datetime.now().astimezone().isoformat(timespec="seconds"))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO playbook_history (
                    captured_at, underlying, expiry, playbook, score, vote, status, rankings_json
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (captured_at, underlying, expiry, str(primary.get("Playbook", "Unknown")),
                 float(primary.get("Score", 0.0)), str(getattr(result, "vote", "WAIT")),
                 str(metadata.get("status", "INACTIVE")), json.dumps(metadata.get("rankings", []), default=str)),
            )

    def get_playbook_history(self, underlying: str, expiry: str, hours: int = 24) -> pd.DataFrame:
        cutoff = (datetime.now().astimezone() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT captured_at, playbook, score, vote, status
                FROM playbook_history
                WHERE underlying = ? AND expiry = ? AND captured_at >= ?
                ORDER BY captured_at
                """, connection, params=(underlying, expiry, cutoff), parse_dates=["captured_at"]
            )

    def purge_older_than(self, days: int = 30) -> int:
        cutoff = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM snapshots WHERE captured_at < ?", (cutoff,))
            return int(cursor.rowcount)
