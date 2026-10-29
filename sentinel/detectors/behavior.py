"""Behavioural rules.

* Fan-in: several hot wallets paying the same address within seconds, a
  pattern that legitimate withdrawal flows practically never produce.
* Unknown initiator: a withdrawal created by a service that never creates withdrawals.
* First payout: a large amount to a destination the exchange has never paid.
* Off-hours: large withdrawals outside staffed hours.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import Signal
from ..state import StateStore
from .base import Context, Detector


class BehaviorDetector(Detector):
    name = "behavior"

    def __init__(self, policy: dict, store: StateStore):
        cfg = policy["behavior"]
        self.store = store
        self.trusted_initiators = {i.lower() for i in cfg.get("trusted_initiators", [])}
        self.unknown_initiator_hard = bool(cfg.get("unknown_initiator_hard_block", True))
        self.fanin_window = int(cfg["fan_in_window_sec"])
        self.fanin_max_sources = int(cfg["fan_in_max_source_wallets"])
        self.fanin_max_requests = int(cfg["fan_in_max_requests"])
        self.first_payout_usd = float(cfg["first_payout_review_usd"])
        self.off_hours = cfg.get("off_hours_utc")  # [start_hour, end_hour]
        self.off_hours_usd = float(cfg.get("off_hours_review_usd", 0))

    def _in_off_hours(self, ts: float) -> bool:
        if not self.off_hours:
            return False
        start, end = self.off_hours
        h = datetime.fromtimestamp(ts, tz=timezone.utc).hour
        return start <= h < end if start <= end else (h >= start or h < end)

    def evaluate(self, ctx: Context) -> list[Signal]:
        req = ctx.request
        out: list[Signal] = []

        # Unknown initiator
        if self.trusted_initiators and req.initiator.lower() not in self.trusted_initiators:
            out.append(self.signal(0.9, f"Initiator '{req.initiator}' is not a trusted withdrawal service",
                                   hard=self.unknown_initiator_hard))

        # Fan-in: count attempts (allowed or not) towards this destination
        since = ctx.now - self.fanin_window
        key = f"fanin:{ctx.dest}"
        self.store.trim(key, since)
        prior_requests = self.store.count_since(key, since)
        self.store.push(key, ctx.now, 1.0)
        src_key = f"fanin_src:{ctx.dest}"
        self.store.hset(src_key, ctx.wallet, str(ctx.now))
        sources = [w for w, ts in self.store.hgetall(src_key).items() if float(ts) >= since]
        if len(sources) >= self.fanin_max_sources:
            out.append(self.signal(1.0, f"{len(sources)} hot wallets paying the same destination "
                                        f"within {self.fanin_window}s", hard=True))
        elif prior_requests + 1 > self.fanin_max_requests:
            out.append(self.signal(0.8, f"{prior_requests + 1} withdrawals to the same destination "
                                        f"within {self.fanin_window}s"))

        # First payout to this destination
        if req.amount_usd >= self.first_payout_usd and not self.store.sismember("paid_dest", ctx.dest):
            out.append(self.signal(0.45, f"First payout to this destination (${req.amount_usd:,.0f})"))

        # Off-hours
        if self.off_hours_usd and req.amount_usd >= self.off_hours_usd and self._in_off_hours(ctx.now):
            out.append(self.signal(0.35, "Large withdrawal outside staffed hours"))
        return out

    def on_allowed(self, ctx: Context) -> None:
        self.store.sadd("paid_dest", ctx.dest)
