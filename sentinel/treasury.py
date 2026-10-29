"""Hot / cold storage ratio monitor.

South Korea's Virtual Asset User Protection Act requires exchanges to keep at
least 80% of customer assets in cold storage. Keeping the hot wallet small caps
the worst-case loss of any hot wallet compromise.
"""
from __future__ import annotations

from .metrics import COLD_RATIO


class TreasuryMonitor:
    def __init__(self, policy: dict):
        cfg = policy.get("treasury", {})
        self.min_cold_ratio = float(cfg.get("min_cold_storage_ratio", 0.8))
        self.max_hot_usd = cfg.get("max_hot_wallet_usd")

    def check(self, hot_usd: float, cold_usd: float) -> dict:
        total = hot_usd + cold_usd
        ratio = cold_usd / total if total > 0 else 1.0
        COLD_RATIO.set(ratio)
        issues = []
        if ratio < self.min_cold_ratio:
            issues.append(f"Cold storage ratio {ratio:.1%} is below the required {self.min_cold_ratio:.0%}")
        if self.max_hot_usd is not None and hot_usd > float(self.max_hot_usd):
            issues.append(f"Hot wallets hold ${hot_usd:,.0f}, above the cap ${float(self.max_hot_usd):,.0f}")
        rebalance = max(0.0, hot_usd - total * (1 - self.min_cold_ratio))
        return {
            "cold_ratio": round(ratio, 6),
            "required_ratio": self.min_cold_ratio,
            "compliant": not issues,
            "issues": issues,
            "move_to_cold_usd": round(rebalance, 2),
        }
