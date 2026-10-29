"""Synthetic withdrawal history for training, and a reference attack simulation."""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import WithdrawalRequest

CSV_FIELDS = ["request_id", "amount_usd", "created_at", "tokens_in_tx", "dest_age_hours", "wallet_share"]


def generate_history(n: int = 20_000, seed: int = 7) -> list[dict]:
    """Plausible retail + institutional withdrawal history (log-normal amounts, daily seasonality)."""
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not security-sensitive
    start = datetime.now(timezone.utc) - timedelta(days=90)
    rows = []
    for i in range(n):
        ts = start + timedelta(seconds=rng.uniform(0, 90 * 86400))
        # busier during Asian and European daytime
        if rng.random() < 0.6:
            ts = ts.replace(hour=rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]))
        institutional = rng.random() < 0.03
        amount = rng.lognormvariate(12.5, 1.0) if institutional else rng.lognormvariate(6.5, 1.6)
        rows.append({
            "request_id": f"hist-{i:06d}",
            "amount_usd": round(min(amount, 1_500_000), 2),
            "created_at": ts.isoformat(),
            "tokens_in_tx": 1,
            "dest_age_hours": round(rng.uniform(1, 72) if rng.random() < 0.05
                                    else rng.uniform(200, 24 * 365 * 4), 2),
            "wallet_share": round(min(1.0, amount / rng.uniform(5e7, 3e8)), 6),
        })
    return rows


def write_csv(rows: list[dict], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return p


ATTACKER = "0x5e7a11000000000000000000000000000000beef"


def drain_scenario() -> list[tuple[WithdrawalRequest, float]]:
    """Reference attack: a compromised signing path sweeps several hot wallets into one fresh address.

    Each tuple is (withdrawal, hot wallet balance in USD before the withdrawal).
    """
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    return [
        (WithdrawalRequest(
            request_id="sim-1", chain="ethereum", asset="USDT", amount=1_200_000_000,
            amount_usd=1_450_000_000, source_wallet="0xhot-wallet-a", destination=ATTACKER,
            initiator="unknown-signer", tokens_in_tx=48, created_at=t0), 1_500_000_000.0),
        (WithdrawalRequest(
            request_id="sim-2", chain="ethereum", asset="ETH", amount=20_000,
            amount_usd=48_000_000, source_wallet="0xhot-wallet-b", destination=ATTACKER,
            initiator="unknown-signer", created_at=t0 + timedelta(seconds=20)), 60_000_000.0),
        (WithdrawalRequest(
            request_id="sim-3", chain="ethereum", asset="USDC", amount=600_000_000,
            amount_usd=600_000_000, source_wallet="0xhot-wallet-c", destination=ATTACKER,
            initiator="unknown-signer", created_at=t0 + timedelta(minutes=15)), 640_000_000.0),
        (WithdrawalRequest(
            request_id="sim-4", chain="ethereum", asset="USDT", amount=950,
            amount_usd=950, source_wallet="0xhot-wallet-d", destination="0x00000000000000000000000000000000c0ffee42",
            initiator="withdrawal-service", created_at=t0 + timedelta(minutes=16)), 40_000_000.0),
    ]
