"""Wire everything together from Settings."""
from __future__ import annotations

from typing import Optional

from .attestation import Attestor
from .audit import AuditLog
from .config import Settings, load_policy
from .engine import SentinelEngine
from .providers import ProviderRegistry, build_registry
from .state import make_store


def build_engine(settings: Settings, registry: Optional[ProviderRegistry] = None) -> SentinelEngine:
    policy = load_policy(settings.policy_path)
    return SentinelEngine(
        policy=policy,
        providers=registry or build_registry(settings),
        store=make_store(settings.redis_url),
        audit=AuditLog(settings.audit_db),
        attestor=Attestor(settings.signing_key, int(policy["attestation"]["ttl_sec"])),
    )
