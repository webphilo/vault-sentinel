"""Queue of withdrawals parked in HOLD until enough operators approve them."""
from __future__ import annotations

import json
import time
from typing import Optional

from .models import Verdict, WithdrawalRequest
from .state import StateStore


class HoldQueue:
    def __init__(self, policy: dict, store: StateStore):
        cfg = policy["holds"]
        self.store = store
        self.required = int(cfg["approvals_required"])
        self.ttl = int(cfg["ttl_sec"])

    def add(self, req: WithdrawalRequest, balance: Optional[float], verdict: Verdict) -> None:
        item = {
            "request": req.model_dump(mode="json"),
            "wallet_balance_usd": balance,
            "verdict": verdict.model_dump(mode="json"),
            "created": time.time(),
            "approvals": [],
        }
        self.store.hset("holds", req.request_id, json.dumps(item))

    def _get(self, request_id: str) -> Optional[dict]:
        raw = self.store.hget("holds", request_id)
        if raw is None:
            return None
        item = json.loads(raw)
        if time.time() - item["created"] > self.ttl:
            self.store.hdel("holds", request_id)  # expired holds are dropped (= rejected)
            return None
        return item

    def list(self) -> list[dict]:
        out = []
        for rid in list(self.store.hgetall("holds")):
            item = self._get(rid)
            if item:
                out.append(item)
        return sorted(out, key=lambda i: i["created"])

    def approve(self, request_id: str, operator: str) -> tuple[Optional[dict], bool]:
        """Returns (item, fully_approved)."""
        item = self._get(request_id)
        if item is None:
            return None, False
        if operator not in item["approvals"]:
            item["approvals"].append(operator)
        if len(item["approvals"]) >= self.required:
            self.store.hdel("holds", request_id)
            return item, True
        self.store.hset("holds", request_id, json.dumps(item))
        return item, False

    def reject(self, request_id: str) -> bool:
        if self._get(request_id) is None:
            return False
        self.store.hdel("holds", request_id)
        return True
