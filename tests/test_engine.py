from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sentinel.engine import combine
from sentinel.models import Decision, Signal
from sentinel.providers import AddressProfile

from .conftest import MIXER, NEW_DEST


def test_normal_withdrawal_is_allowed_and_attested(engine, make_req):
    v = engine.screen(make_req(), wallet_balance_usd=50_000_000)
    assert v.decision is Decision.ALLOW
    assert v.attestation is not None


def test_fresh_address_goes_to_hold(engine, make_req):
    v = engine.screen(make_req(destination=NEW_DEST), wallet_balance_usd=50_000_000)
    assert v.decision is Decision.HOLD
    assert engine.holds.list()


def test_mixer_funded_destination_is_blocked(engine, provider, make_req):
    dest = "0x00000000000000000000000000000000000000cc"
    provider.add(AddressProfile(address=dest, tx_count=3, funded_by=[MIXER],
                                first_seen=datetime.now(timezone.utc) - timedelta(hours=2)))
    v = engine.screen(make_req(destination=dest))
    assert v.decision is Decision.BLOCK
    assert any("mixer" in s.reason.lower() for s in v.signals)


def test_wallet_sweep_is_blocked(engine, make_req):
    v = engine.screen(make_req(tokens_in_tx=63))
    assert v.decision is Decision.BLOCK


def test_unknown_initiator_is_blocked(engine, make_req):
    v = engine.screen(make_req(initiator="mystery-service"))
    assert v.decision is Decision.BLOCK


def test_breaker_freezes_all_wallets_after_multi_wallet_attack(engine, make_req):
    engine.screen(make_req(source_wallet="0xhotA", tokens_in_tx=50))
    engine.screen(make_req(source_wallet="0xhotB", tokens_in_tx=50))
    v = engine.screen(make_req(source_wallet="0xhotC"))
    assert v.decision is Decision.BLOCK
    assert v.breaker_tripped


def test_breaker_reset_requires_two_operators(engine, make_req):
    engine.breaker.trip("0xhot1")
    assert not engine.breaker.approve_reset("0xhot1", "alice")
    assert not engine.breaker.approve_reset("0xhot1", "alice")  # same operator twice
    assert engine.breaker.approve_reset("0xhot1", "bob")
    assert engine.screen(make_req()).decision is Decision.ALLOW


def test_hold_approval_flow(engine, make_req):
    req = make_req(destination=NEW_DEST)
    assert engine.screen(req).decision is Decision.HOLD
    assert engine.approve_hold(req.request_id, "alice") is None
    final = engine.approve_hold(req.request_id, "bob")
    assert final is not None and final.decision is Decision.ALLOW
    assert final.attestation is not None


def test_combine_formula():
    s = [Signal(detector="a", score=0.5, reason=""), Signal(detector="b", score=0.5, reason="")]
    assert combine(s) == 0.75


def test_audit_chain_is_intact(engine, make_req):
    for _ in range(5):
        engine.screen(make_req())
    ok, broken = engine.audit.verify_chain()
    assert ok and broken is None
