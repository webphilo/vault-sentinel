"""Chain -> provider routing."""
from __future__ import annotations

import logging

from ..config import Settings
from .base import CachedProvider, ChainDataProvider, UnavailableProvider
from .bitcoin import EsploraProvider
from .evm import CHAIN_IDS, EtherscanProvider
from .solana import SolanaRpcProvider
from .static import StaticProvider
from .tron import TronGridProvider

log = logging.getLogger("sentinel.providers")


class ProviderRegistry:
    def __init__(self, default: ChainDataProvider | None = None):
        self._providers: dict[str, ChainDataProvider] = {}
        self._default = default or UnavailableProvider()

    def register(self, chain: str, provider: ChainDataProvider) -> None:
        self._providers[chain.lower()] = provider

    def get(self, chain: str) -> ChainDataProvider:
        return self._providers.get(chain.lower(), self._default)

    @property
    def chains(self) -> list[str]:
        return sorted(self._providers)


def build_registry(settings: Settings, ttl_sec: float = 60.0) -> ProviderRegistry:
    if settings.dev_mode:
        log.warning("DEV MODE: using StaticProvider for every chain, do not use in production")
        return ProviderRegistry(default=StaticProvider())

    reg = ProviderRegistry()
    if settings.etherscan_api_key:
        for chain in CHAIN_IDS:
            reg.register(chain, CachedProvider(EtherscanProvider(chain, settings.etherscan_api_key), ttl_sec))
    else:
        log.warning("ETHERSCAN_API_KEY not set: EVM withdrawals will fail closed (HOLD)")
    reg.register("tron", CachedProvider(TronGridProvider(settings.trongrid_api_key), ttl_sec))
    reg.register("solana", CachedProvider(SolanaRpcProvider(settings.solana_rpc_url), ttl_sec))
    reg.register("bitcoin", CachedProvider(EsploraProvider(settings.bitcoin_api_url), ttl_sec))
    return reg
