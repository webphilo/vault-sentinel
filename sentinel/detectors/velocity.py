"""Outflow velocity limits.

On 29 Oct 2026 billions left the hot wallets within ~40 minutes, the first
transaction alone carrying 63 different tokens. Per-transaction caps, a
share-of-wallet cap and sliding windows (per wallet and exchange-wide) stop
such an outflow at the first breach.
"""
from __future__ import annotations

from ..models import Signal
from ..state import StateStore
from .base import Context, Detector

GLOBAL = "__global__"


class VelocityDetector(Detector):
    name = "velocity"

    def __init__(self, policy: dict, store: StateStore):
        cfg = policy["velocity"]
        self.store = store
        self.max_single = float(cfg["max_single_tx_usd"])
        self.max_tokens = int(cfg["max_tokens_per_tx"])
        self.max_share = float(cfg["max_share_of_wallet_per_tx"])
        self.windows = cfg["wallet_windows"]
        self.global_windows = cfg.get("global_windows", [])
        self.per_asset = {k.upper(): float(v) for k, v in (cfg.get("per_asset_max_single_tx_usd") or {}).items()}
        self._max_window = max([w["window_sec"] for w in self.windows + self.global_windows] or [86400])

    def _check_windows(self, key: str, windows: list[dict], amount: float, now: float, label: str) -> list[Signal]:
        out = []
        self.store.trim(f"vel:{key}", now - self._max_window)
        for w in windows:
            projected = self.store.sum_since(f"vel:{key}", now - w["window_sec"]) + amount
            if projected > w["max_usd"]:
                out.append(self.signal(
                    1.0,
                    f"{label} outflow ${projected:,.0f} in {w['window_sec'] // 60} min exceeds ${w['max_usd']:,.0f}",
                    hard=True,
                ))
        return out

    def evaluate(self, ctx: Context) -> list[Signal]:
        req = ctx.request
        out: list[Signal] = []

        cap = self.per_asset.get(req.asset.upper(), self.max_single)
        if req.amount_usd > cap:
            out.append(self.signal(1.0, f"Single tx ${req.amount_usd:,.0f} exceeds cap ${cap:,.0f}", hard=True))

        if req.tokens_in_tx > self.max_tokens:
            out.append(self.signal(1.0, f"{req.tokens_in_tx} assets in one tx (wallet sweep pattern)", hard=True))

        bal = ctx.wallet_balance_usd
        if bal and bal > 0:
            share = req.amount_usd / bal
            if share > self.max_share:
                out.append(self.signal(1.0, f"Tx drains {share:.0%} of the hot wallet balance", hard=True))

        out += self._check_windows(ctx.wallet, self.windows, req.amount_usd, ctx.now, "Wallet")
        out += self._check_windows(GLOBAL, self.global_windows, req.amount_usd, ctx.now, "Exchange-wide")
        return out

    def on_allowed(self, ctx: Context) -> None:
        amt = ctx.request.amount_usd
        self.store.push(f"vel:{ctx.wallet}", ctx.now, amt)
        self.store.push(f"vel:{GLOBAL}", ctx.now, amt)
