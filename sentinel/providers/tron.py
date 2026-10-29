"""Tron via TronGrid."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .base import AddressProfile, ChainDataProvider

TRONGRID = "https://api.trongrid.io/v1/accounts/{address}/transactions"


class TronGridProvider(ChainDataProvider):
    def __init__(self, api_key: str = "", client: httpx.Client | None = None):
        headers = {"TRON-PRO-API-KEY": api_key} if api_key else {}
        self.client = client or httpx.Client(timeout=4.0, headers=headers)

    def profile(self, address: str) -> AddressProfile:
        try:
            r = self.client.get(
                TRONGRID.format(address=address),
                params={"limit": 50, "order_by": "block_timestamp,asc"},
            )
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return AddressProfile(address=address, available=False)

        txs = data.get("data") or []
        if not txs:
            return AddressProfile(address=address, tx_count=0)

        funded_by = []
        for t in txs[:5]:
            try:
                owner = t["raw_data"]["contract"][0]["parameter"]["value"]["owner_address"]
                funded_by.append(str(owner).lower())
            except (KeyError, IndexError, TypeError):
                continue

        return AddressProfile(
            address=address,
            first_seen=datetime.fromtimestamp(int(txs[0]["block_timestamp"]) / 1000, tz=timezone.utc),
            tx_count=len(txs),
            funded_by=funded_by,
        )
