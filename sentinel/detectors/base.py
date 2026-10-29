"""Detector interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..models import Signal, WithdrawalRequest
from ..providers.base import AddressProfile


@dataclass
class Context:
    request: WithdrawalRequest
    wallet_balance_usd: Optional[float]
    profile: Optional[AddressProfile]
    now: float  # unix seconds

    @property
    def dest(self) -> str:
        return self.request.destination.lower()

    @property
    def wallet(self) -> str:
        return self.request.source_wallet.lower()

    @property
    def dest_age_hours(self) -> Optional[float]:
        p = self.profile
        if p is None or not p.available or p.first_seen is None:
            return None
        return max(0.0, (self.now - p.first_seen.timestamp()) / 3600)


class Detector(ABC):
    name: str = "detector"

    @abstractmethod
    def evaluate(self, ctx: Context) -> list[Signal]:
        """Return risk signals. Must not mutate state that depends on the final decision."""

    def on_allowed(self, ctx: Context) -> None:
        """Called once the withdrawal is approved (ALLOW or approved HOLD)."""

    def signal(self, score: float, reason: str, hard: bool = False) -> Signal:
        return Signal(detector=self.name, score=min(1.0, max(0.0, score)), reason=reason, hard_block=hard)
