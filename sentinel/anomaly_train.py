"""Turn a withdrawal-history CSV into model features.

Required columns: amount_usd, created_at (ISO 8601)
Optional columns: tokens_in_tx, dest_age_hours, wallet_share
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterator

import numpy as np

from .detectors.anomaly import featurize


def _float(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def rows_from_csv(path: str | Path) -> Iterator[np.ndarray]:
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            yield featurize(
                amount_usd=float(r["amount_usd"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                tokens_in_tx=int(r.get("tokens_in_tx") or 1),
                dest_age_hours=_float(r.get("dest_age_hours")),
                wallet_share=_float(r.get("wallet_share")),
            )
