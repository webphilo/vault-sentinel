"""EVM chains via Etherscan API v2 (one key covers all supported chains)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from .base import AddressProfile, ChainDataProvider

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"

CHAIN_IDS = {
    "ethereum": 1,
    "bsc": 56,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
}


class EtherscanProvider(ChainDataProvider):
    def __init__(self, chain: str, api_key: str, client: Optional[httpx.Client] = None):
        if chain not in CHAIN_IDS:
            raise ValueError(f"unsupported EVM chain: {chain}")
        self.chain_id = CHAIN_IDS[chain]
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=4.0)

    def _txlist(self, address: str, action: str) -> Optional[list]:
        params = {
            "chainid": self.chain_id,
            "module": "account",
            "action": action,
            "address": address,
            "startblock": 0,
            "endblock": 999_999_999,
            "page": 1,
            "offset": 100,
            "sort": "asc",
            "apikey": self.api_key,
        }
        try:
            r = self.client.get(ETHERSCAN_V2, params=params)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return None
        result = data.get("result")
        if isinstance(result, list):
            return result
        return None  # error string such as "Max rate limit reached"

    def profile(self, address: str) -> AddressProfile:
        normal = self._txlist(address, "txlist")
        tokens = self._txlist(address, "tokentx")
        if normal is None and tokens is None:
            return AddressProfile(address=address, available=False)

        txs = sorted((normal or []) + (tokens or []), key=lambda t: int(t.get("timeStamp", 0)))
        if not txs:
            return AddressProfile(address=address, tx_count=0)

        addr = address.lower()
        funded_by = []
        for t in (normal or [])[:5]:
            if t.get("to", "").lower() == addr and t.get("from"):
                funded_by.append(t["from"].lower())

        return AddressProfile(
            address=address,
            first_seen=datetime.fromtimestamp(int(txs[0]["timeStamp"]), tz=timezone.utc),
            tx_count=len(txs),
            funded_by=funded_by,
        )
