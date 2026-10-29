"""Synthetic history for training, and a replay of the 29 Oct 2026 incident."""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import WithdrawalRequest

CSV_FIELDS = ["request_id", "amount_usd", "created_at", "tokens_in_tx", "dest_age_hours", "wallet_share"]


def generate_history(n: int = 20_000, seed: int = 7) -> list[dict]:
    """Plausible retail + institutional withdrawal history (log-normal amounts, daily seasonality)."""
    rng = random.Random(seed)
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


ATTACKER = "0xattacker00000000000000000000000000000001"


def incident_scenario() -> list[tuple[WithdrawalRequest, float]]:
    """Approximation of the public on-chain timeline of 29 Oct 2026 (figures rounded)."""
    t0 = datetime(2026, 10, 29, 20, 24, 23, tzinfo=timezone.utc)
    return [
        (WithdrawalRequest(
            request_id="replay-1", chain="ethereum", asset="USDT", amount=1_600_000_000,
            amount_usd=1_600_000_000 + 388_000_000, source_wallet="0xbinance14", destination=ATTACKER,
            initiator="unknown-signer", tokens_in_tx=64, created_at=t0), 2_100_000_000.0),
        (WithdrawalRequest(
            request_id="replay-2", chain="ethereum", asset="ETH", amount=28_000,
            amount_usd=65_000_000, source_wallet="0xbinance16", destination=ATTACKER,
            initiator="unknown-signer", created_at=t0 + timedelta(seconds=24)), 70_000_000.0),
        (WithdrawalRequest(
            request_id="replay-3", chain="ethereum", asset="USDC", amount=780_000_000,
            amount_usd=780_000_000, source_wallet="0xhotwallet34", destination=ATTACKER,
            initiator="unknown-signer", created_at=t0 + timedelta(minutes=17)), 800_000_000.0),
        (WithdrawalRequest(
            request_id="replay-4", chain="ethereum", asset="USDT", amount=950,
            amount_usd=950, source_wallet="0xhotwallet20", destination="0xretailuser000000000000000000000000000042",
            initiator="withdrawal-service", created_at=t0 + timedelta(minutes=18)), 40_000_000.0),
    ]
