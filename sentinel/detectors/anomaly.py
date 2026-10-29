"""AI anomaly detection.

Two complementary models:

1. **Isolation Forest** trained offline on the exchange's own withdrawal history
   (amount, time of day, weekday, assets per tx, destination age, share of wallet).
2. **Online baseline** per hot wallet: a running mean / variance of log(amount)
   (Welford's algorithm) that adapts continuously and flags sudden outliers.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from ..models import Signal
from ..state import StateStore
from .base import Context, Detector

log = logging.getLogger("sentinel.anomaly")

FEATURES = [
    "log_amount_usd",
    "hour_sin",
    "hour_cos",
    "weekday",
    "tokens_in_tx",
    "log_dest_age_hours",
    "wallet_share",
]

MAX_AGE_H = 24 * 365


def featurize(
    amount_usd: float,
    created_at: datetime,
    tokens_in_tx: int,
    dest_age_hours: Optional[float],
    wallet_share: Optional[float],
) -> np.ndarray:
    ts = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    hour = ts.hour + ts.minute / 60
    age = 0.0 if dest_age_hours is None else min(dest_age_hours, MAX_AGE_H)
    return np.array(
        [
            math.log1p(amount_usd),
            math.sin(2 * math.pi * hour / 24),
            math.cos(2 * math.pi * hour / 24),
            float(ts.weekday()),
            float(tokens_in_tx),
            math.log1p(age),
            min(1.0, wallet_share or 0.0),
        ],
        dtype=float,
    )


def featurize_ctx(ctx: Context) -> np.ndarray:
    req = ctx.request
    share = None
    if ctx.wallet_balance_usd:
        share = req.amount_usd / ctx.wallet_balance_usd
    return featurize(req.amount_usd, req.created_at, req.tokens_in_tx, ctx.dest_age_hours, share)


class AnomalyDetector(Detector):
    name = "ai_anomaly"

    def __init__(self, policy: dict, store: StateStore):
        cfg = policy["anomaly"]
        self.store = store
        base = Path(policy.get("_base_dir", "."))
        mp = Path(cfg["model_path"])
        self.model_path = mp if mp.is_absolute() else (base.parent / mp)
        self.threshold = float(cfg["score_threshold"])
        self.contamination = float(cfg["contamination"])
        self.z_threshold = float(cfg.get("online_z_threshold", 4.0))
        self.min_samples = int(cfg.get("online_min_samples", 50))
        self.model = None
        self._load()

    # ---- offline model ---------------------------------------------------
    def _load(self) -> None:
        if self.model_path.exists():
            try:
                import joblib

                self.model = joblib.load(self.model_path)
                log.info("Loaded anomaly model from %s", self.model_path)
            except Exception:  # corrupted model must not take the service down
                log.exception("Failed to load anomaly model")
                self.model = None

    @property
    def trained(self) -> bool:
        return self.model is not None

    def train(self, rows: Iterable[np.ndarray], n_estimators: int = 300) -> int:
        import joblib
        from sklearn.ensemble import IsolationForest

        X = np.vstack(list(rows))
        self.model = IsolationForest(
            n_estimators=n_estimators, contamination=self.contamination, random_state=42
        ).fit(X)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, self.model_path)
        return int(X.shape[0])

    def model_score(self, x: np.ndarray) -> float:
        """0 = normal, 1 = strongly anomalous."""
        if self.model is None:
            return 0.0
        raw = float(-self.model.score_samples(x.reshape(1, -1))[0])  # ~0.35 normal, >0.6 anomalous
        return 1.0 / (1.0 + math.exp(-14.0 * (raw - 0.55)))

    # ---- online baseline -------------------------------------------------
    def _baseline(self, wallet: str) -> tuple[int, float, float]:
        h = self.store.hgetall(f"baseline:{wallet}")
        return int(h.get("n", 0)), float(h.get("mean", 0.0)), float(h.get("m2", 0.0))

    def online_z(self, wallet: str, amount_usd: float) -> Optional[float]:
        n, mean, m2 = self._baseline(wallet)
        if n < self.min_samples:
            return None
        std = math.sqrt(m2 / (n - 1)) if n > 1 else 0.0
        if std <= 1e-9:
            return None
        return (math.log1p(amount_usd) - mean) / std

    # ---- detector API ----------------------------------------------------
    def evaluate(self, ctx: Context) -> list[Signal]:
        out: list[Signal] = []
        s = self.model_score(featurize_ctx(ctx))
        if s >= self.threshold:
            out.append(self.signal(s, f"AI model: withdrawal deviates from learned profile (score {s:.2f})"))

        z = self.online_z(ctx.wallet, ctx.request.amount_usd)
        if z is not None and z >= self.z_threshold:
            score = min(0.9, 0.4 + 0.1 * (z - self.z_threshold))
            out.append(self.signal(score, f"Amount is {z:.1f} sigma above this wallet's baseline"))
        return out

    def on_allowed(self, ctx: Context) -> None:
        key = f"baseline:{ctx.wallet}"
        n, mean, m2 = self._baseline(ctx.wallet)
        x = math.log1p(ctx.request.amount_usd)
        n += 1
        delta = x - mean
        mean += delta / n
        m2 += delta * (x - mean)
        self.store.hset(key, "n", str(n))
        self.store.hset(key, "mean", repr(mean))
        self.store.hset(key, "m2", repr(m2))
