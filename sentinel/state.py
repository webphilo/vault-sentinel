"""Shared state: in-memory for a single node, Redis for a horizontally scaled cluster.

All detectors, the circuit breaker and the hold queue keep their state here, so
several VaultSentinel replicas see the same velocity windows and the same frozen wallets.
"""
from __future__ import annotations

import threading
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Optional


class StateStore(ABC):
    # time series ---------------------------------------------------------
    @abstractmethod
    def push(self, key: str, ts: float, value: float) -> None: ...
    @abstractmethod
    def sum_since(self, key: str, since: float) -> float: ...
    @abstractmethod
    def count_since(self, key: str, since: float) -> int: ...
    @abstractmethod
    def trim(self, key: str, before: float) -> None: ...

    # sets ----------------------------------------------------------------
    @abstractmethod
    def sadd(self, key: str, member: str) -> None: ...
    @abstractmethod
    def sismember(self, key: str, member: str) -> bool: ...

    # hashes --------------------------------------------------------------
    @abstractmethod
    def hset(self, key: str, field: str, value: str) -> None: ...
    @abstractmethod
    def hget(self, key: str, field: str) -> Optional[str]: ...
    @abstractmethod
    def hdel(self, key: str, field: str) -> None: ...
    @abstractmethod
    def hgetall(self, key: str) -> dict[str, str]: ...

    # misc ----------------------------------------------------------------
    @abstractmethod
    def delete(self, key: str) -> None: ...


class MemoryStore(StateStore):
    def __init__(self) -> None:
        self._z: dict[str, deque[tuple[float, float]]] = defaultdict(deque)
        self._s: dict[str, set[str]] = defaultdict(set)
        self._h: dict[str, dict[str, str]] = defaultdict(dict)
        self._lock = threading.RLock()

    def push(self, key: str, ts: float, value: float) -> None:
        with self._lock:
            self._z[key].append((ts, value))

    def sum_since(self, key: str, since: float) -> float:
        with self._lock:
            return sum(v for t, v in self._z.get(key, ()) if t >= since)

    def count_since(self, key: str, since: float) -> int:
        with self._lock:
            return sum(1 for t, _ in self._z.get(key, ()) if t >= since)

    def trim(self, key: str, before: float) -> None:
        with self._lock:
            q = self._z.get(key)
            while q and q[0][0] < before:
                q.popleft()

    def sadd(self, key: str, member: str) -> None:
        with self._lock:
            self._s[key].add(member)

    def sismember(self, key: str, member: str) -> bool:
        with self._lock:
            return member in self._s.get(key, ())

    def hset(self, key: str, field: str, value: str) -> None:
        with self._lock:
            self._h[key][field] = value

    def hget(self, key: str, field: str) -> Optional[str]:
        with self._lock:
            return self._h.get(key, {}).get(field)

    def hdel(self, key: str, field: str) -> None:
        with self._lock:
            self._h.get(key, {}).pop(field, None)

    def hgetall(self, key: str) -> dict[str, str]:
        with self._lock:
            return dict(self._h.get(key, {}))

    def delete(self, key: str) -> None:
        with self._lock:
            self._z.pop(key, None)
            self._s.pop(key, None)
            self._h.pop(key, None)


class RedisStore(StateStore):
    def __init__(self, url: str, prefix: str = "vs:") -> None:
        import redis  # optional dependency

        self.r = redis.Redis.from_url(url, decode_responses=True)
        self.p = prefix

    def _k(self, key: str) -> str:
        return self.p + key

    def push(self, key: str, ts: float, value: float) -> None:
        self.r.zadd(self._k(key), {f"{ts}:{value}:{uuid.uuid4().hex}": ts})

    def sum_since(self, key: str, since: float) -> float:
        members = self.r.zrangebyscore(self._k(key), since, "+inf")
        return sum(float(m.split(":")[1]) for m in members)

    def count_since(self, key: str, since: float) -> int:
        return int(self.r.zcount(self._k(key), since, "+inf"))

    def trim(self, key: str, before: float) -> None:
        self.r.zremrangebyscore(self._k(key), "-inf", f"({before}")

    def sadd(self, key: str, member: str) -> None:
        self.r.sadd(self._k(key), member)

    def sismember(self, key: str, member: str) -> bool:
        return bool(self.r.sismember(self._k(key), member))

    def hset(self, key: str, field: str, value: str) -> None:
        self.r.hset(self._k(key), field, value)

    def hget(self, key: str, field: str) -> Optional[str]:
        return self.r.hget(self._k(key), field)

    def hdel(self, key: str, field: str) -> None:
        self.r.hdel(self._k(key), field)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.r.hgetall(self._k(key)))

    def delete(self, key: str) -> None:
        self.r.delete(self._k(key))


def make_store(url: Optional[str]) -> StateStore:
    if url and url.startswith(("redis://", "rediss://")):
        return RedisStore(url)
    return MemoryStore()
