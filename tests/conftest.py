from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sentinel.attestation import Attestor
from sentinel.audit import AuditLog
from sentinel.config import DEFAULT_POLICY, load_policy
from sentinel.engine import SentinelEngine
from sentinel.models import WithdrawalRequest
from sentinel.providers import AddressProfile, ProviderRegistry, StaticProvider
from sentinel.state import MemoryStore

OLD_DEST = "0x00000000000000000000000000000000000000aa"
NEW_DEST = "0x00000000000000000000000000000000000000bb"
MIXER = "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"


@pytest.fixture
def policy() -> dict:
    p = load_policy(DEFAULT_POLICY)
    p["anomaly"]["model_path"] = "models/__test_does_not_exist__.joblib"
    p["behavior"]["off_hours_utc"] = None
    return p


@pytest.fixture
def provider() -> StaticProvider:
    sp = StaticProvider()
    sp.add(AddressProfile(address=OLD_DEST, tx_count=500,
                          first_seen=datetime.now(timezone.utc) - timedelta(days=400)))
    return sp


@pytest.fixture
def engine(policy, provider) -> SentinelEngine:
    return SentinelEngine(policy, ProviderRegistry(default=provider), MemoryStore(),
                          AuditLog(":memory:"), Attestor(None, 120))


@pytest.fixture
def make_req():
    counter = {"n": 0}

    def _make(**kw) -> WithdrawalRequest:
        counter["n"] += 1
        base = dict(
            request_id=f"t-{counter['n']}", chain="ethereum", asset="USDT", amount=1000.0,
            amount_usd=1000.0, source_wallet="0xhot1", destination=OLD_DEST,
            initiator="withdrawal-service",
        )
        base.update(kw)
        return WithdrawalRequest(**base)

    return _make
