"""Provider interface and helpers."""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AddressProfile:
    address: str
    first_seen: datetime | None = None
    tx_count: int = 0
    funded_by: list[str] = field(default_factory=list)  # who sent the first funds/gas
    labels: set[str] = field(default_factory=set)       # "mixer", "sanctioned", "exchange", ...
    available: bool = True                               # False = data source failed

    @property
    def is_new(self) -> bool:
        return self.available and (self.tx_count == 0 or self.first_seen is None)


class ChainDataProvider(ABC):
    @abstractmethod
    def profile(self, address: str) -> AddressProfile: ...


class UnavailableProvider(ChainDataProvider):
    """Used for chains without a configured provider: fail closed."""

    def profile(self, address: str) -> AddressProfile:
        return AddressProfile(address=address, available=False)


class CachedProvider(ChainDataProvider):
    """Short TTL cache so bursts of withdrawals do not hammer the indexer."""

    def __init__(self, inner: ChainDataProvider, ttl_sec: float = 60.0, max_items: int = 50_000):
        self.inner = inner
        self.ttl = ttl_sec
        self.max_items = max_items
        self._cache: dict[str, tuple[float, AddressProfile]] = {}
        self._lock = threading.Lock()

    def profile(self, address: str) -> AddressProfile:
        key = address.lower()
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        prof = self.inner.profile(address)
        if prof.available:  # never cache failures
            with self._lock:
                if len(self._cache) >= self.max_items:
                    self._cache.clear()
                self._cache[key] = (now, prof)
        return prof
