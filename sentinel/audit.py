"""Tamper-evident audit log.

Every decision is appended to SQLite. Each row stores the SHA-256 of the
previous row, so editing or deleting any past record breaks the chain and is
detected by `verify_chain()` / `sentinel verify-audit`.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    event       TEXT    NOT NULL,
    request_id  TEXT,
    decision    TEXT,
    risk        REAL,
    actor       TEXT,
    payload     TEXT    NOT NULL,
    prev_hash   TEXT    NOT NULL,
    hash        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_request ON audit(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_decision ON audit(decision);
"""


def _row_hash(prev: str, ts: str, event: str, request_id: Optional[str], decision: Optional[str],
              risk: Optional[float], actor: Optional[str], payload: str) -> str:
    material = json.dumps([prev, ts, event, request_id, decision, risk, actor, payload],
                          separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode()).hexdigest()


class AuditLog:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    def _last_hash(self) -> str:
        row = self._db.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        return row[0] if row else GENESIS

    def append(self, event: str, payload: dict[str, Any], request_id: Optional[str] = None,
               decision: Optional[str] = None, risk: Optional[float] = None,
               actor: Optional[str] = None) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        with self._lock:
            prev = self._last_hash()
            h = _row_hash(prev, ts, event, request_id, decision, risk, actor, body)
            self._db.execute(
                "INSERT INTO audit(ts,event,request_id,decision,risk,actor,payload,prev_hash,hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, event, request_id, decision, risk, actor, body, prev, h),
            )
        return h

    def recent(self, limit: int = 100, decision: Optional[str] = None) -> list[dict[str, Any]]:
        q = "SELECT id,ts,event,request_id,decision,risk,actor,payload FROM audit"
        args: list[Any] = []
        if decision:
            q += " WHERE decision = ?"
            args.append(decision)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        rows = self._db.execute(q, args).fetchall()
        return [
            {"id": r[0], "ts": r[1], "event": r[2], "request_id": r[3], "decision": r[4],
             "risk": r[5], "actor": r[6], "payload": json.loads(r[7])}
            for r in rows
        ]

    def stats(self, since_iso: Optional[str] = None) -> dict[str, int]:
        q = "SELECT decision, COUNT(*) FROM audit WHERE event = 'screen'"
        args: list[Any] = []
        if since_iso:
            q += " AND ts >= ?"
            args.append(since_iso)
        q += " GROUP BY decision"
        return {d: n for d, n in self._db.execute(q, args).fetchall() if d}

    def verify_chain(self) -> tuple[bool, Optional[int]]:
        """Returns (ok, first_broken_id)."""
        prev = GENESIS
        cur = self._db.execute(
            "SELECT id,ts,event,request_id,decision,risk,actor,payload,prev_hash,hash FROM audit ORDER BY id"
        )
        for row in cur:
            rid, ts, event, req_id, decision, risk, actor, payload, prev_hash, h = row
            if prev_hash != prev or _row_hash(prev, ts, event, req_id, decision, risk, actor, payload) != h:
                return False, rid
            prev = h
        return True, None
