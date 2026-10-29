"""Prometheus metrics."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

DECISIONS = Counter("sentinel_decisions_total", "Screening decisions", ["decision", "chain"])
SIGNALS = Counter("sentinel_signals_total", "Risk signals raised", ["detector", "hard"])
LATENCY = Histogram(
    "sentinel_screen_latency_seconds", "End-to-end screening latency",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
USD_BLOCKED = Counter("sentinel_usd_blocked_total", "USD value of blocked withdrawals", ["chain"])
USD_ALLOWED = Counter("sentinel_usd_allowed_total", "USD value of allowed withdrawals", ["chain"])
BREAKER_TRIPPED = Gauge("sentinel_breaker_tripped_wallets", "Wallets currently frozen by the circuit breaker")
HOLDS_PENDING = Gauge("sentinel_holds_pending", "Withdrawals waiting for manual approval")
COLD_RATIO = Gauge("sentinel_cold_storage_ratio", "Last reported cold / (hot + cold) ratio")
