"""Solana via JSON-RPC getSignaturesForAddress."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .base import AddressProfile, ChainDataProvider


class SolanaRpcProvider(ChainDataProvider):
    def __init__(self, rpc_url: str, client: httpx.Client | None = None):
        self.rpc_url = rpc_url
        self.client = client or httpx.Client(timeout=4.0)

    def profile(self, address: str) -> AddressProfile:
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [address, {"limit": 1000}],
        }
        try:
            r = self.client.post(self.rpc_url, json=body)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return AddressProfile(address=address, available=False)

        if "error" in data:
            return AddressProfile(address=address, available=False)
        sigs = data.get("result") or []
        if not sigs:
            return AddressProfile(address=address, tx_count=0)

        oldest = sigs[-1]  # newest first
        block_time = oldest.get("blockTime")
        first_seen = (
            datetime.fromtimestamp(int(block_time), tz=timezone.utc) if block_time else None
        )
        return AddressProfile(address=address, first_seen=first_seen, tx_count=len(sigs))
