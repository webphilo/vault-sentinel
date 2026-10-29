"""Bitcoin via an Esplora-compatible API (mempool.space, Blockstream, self-hosted)."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .base import AddressProfile, ChainDataProvider


class EsploraProvider(ChainDataProvider):
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=4.0)

    def profile(self, address: str) -> AddressProfile:
        try:
            info = self.client.get(f"{self.base}/address/{address}")
            info.raise_for_status()
            stats = info.json()
            txs_resp = self.client.get(f"{self.base}/address/{address}/txs")
            txs_resp.raise_for_status()
            txs = txs_resp.json()
        except (httpx.HTTPError, ValueError):
            return AddressProfile(address=address, available=False)

        tx_count = int(stats.get("chain_stats", {}).get("tx_count", 0)) + int(
            stats.get("mempool_stats", {}).get("tx_count", 0)
        )
        if tx_count == 0:
            return AddressProfile(address=address, tx_count=0)

        # The endpoint returns newest first; the oldest one we see is an upper bound on age.
        times = [t["status"]["block_time"] for t in txs if t.get("status", {}).get("block_time")]
        first_seen = datetime.fromtimestamp(min(times), tz=timezone.utc) if times else None
        return AddressProfile(address=address, first_seen=first_seen, tx_count=tx_count)
