"""In-memory provider for development, demos and tests."""
from __future__ import annotations

from typing import Optional

from .base import AddressProfile, ChainDataProvider


class StaticProvider(ChainDataProvider):
    """Returns preset profiles; any unknown address looks brand new."""

    def __init__(self, profiles: Optional[dict[str, AddressProfile]] = None):
        self.profiles = {k.lower(): v for k, v in (profiles or {}).items()}

    def add(self, profile: AddressProfile) -> None:
        self.profiles[profile.address.lower()] = profile

    def profile(self, address: str) -> AddressProfile:
        return self.profiles.get(address.lower(), AddressProfile(address=address, tx_count=0))
