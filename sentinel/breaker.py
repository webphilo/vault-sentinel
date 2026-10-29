"""Circuit breaker for hot wallets.

* Wallet level: N hard blocks on one wallet within the window freeze that wallet.
* Exchange level: hard blocks on several distinct wallets within the window
  freeze EVERY hot wallet (a coordinated multi-wallet drain).

Unfreezing requires approvals from M distinct operators (four-eyes principle).
"""
from __future__ import annotations

import time

from .state import StateStore

ALL = "__all__"


class CircuitBreaker:
    def __init__(self, policy: dict, store: StateStore):
        cfg = policy["circuit_breaker"]
        self.store = store
        self.trip_after = int(cfg["trip_after_hard_blocks"])
        self.window = int(cfg["window_sec"])
        self.global_wallets = int(cfg["global_trip_after_wallets"])
        self.reset_approvals = int(cfg["reset_requires_approvals"])

    # --- state -------------------------------------------------------------
    def is_tripped(self, wallet: str) -> bool:
        tripped = self.store.hgetall("breaker")
        return ALL in tripped or wallet.lower() in tripped

    def status(self) -> dict[str, dict]:
        out = {}
        for wallet, raw in self.store.hgetall("breaker").items():
            ts, _, reason = raw.partition("|")
            votes = sorted(self.store.hgetall(f"breaker_votes:{wallet}"))
            out[wallet] = {"since": float(ts), "reason": reason, "reset_votes": votes,
                           "votes_required": self.reset_approvals}
        return out

    # --- transitions ---------------------------------------------------------
    def trip(self, wallet: str, reason: str = "manual") -> None:
        self.store.hset("breaker", wallet.lower(), f"{time.time()}|{reason}")
        self.store.delete(f"breaker_votes:{wallet.lower()}")

    def record_hard_block(self, wallet: str) -> bool:
        """Register a hard block. Returns True if this call tripped a breaker."""
        now = time.time()
        wallet = wallet.lower()
        since = now - self.window

        key = f"blocks:{wallet}"
        self.store.trim(key, since)
        self.store.push(key, now, 1.0)
        self.store.hset("blocked_wallets", wallet, str(now))

        tripped = False
        if self.store.count_since(key, since) >= self.trip_after and not self.is_tripped(wallet):
            self.trip(wallet, f"{self.trip_after} hard blocks within {self.window}s")
            tripped = True

        recent = [w for w, ts in self.store.hgetall("blocked_wallets").items() if float(ts) >= since]
        if len(recent) >= self.global_wallets and ALL not in self.store.hgetall("breaker"):
            self.trip(ALL, f"hard blocks on {len(recent)} distinct hot wallets within {self.window}s")
            tripped = True
        return tripped

    def approve_reset(self, wallet: str, operator: str) -> bool:
        wallet = wallet.lower()
        if wallet not in self.store.hgetall("breaker"):
            return True
        votes_key = f"breaker_votes:{wallet}"
        self.store.hset(votes_key, operator, str(time.time()))
        if len(self.store.hgetall(votes_key)) >= self.reset_approvals:
            self.store.hdel("breaker", wallet)
            self.store.delete(votes_key)
            self.store.delete(f"blocks:{wallet}")
            if wallet == ALL:
                self.store.delete("blocked_wallets")
            else:
                self.store.hdel("blocked_wallets", wallet)
            return True
        return False
