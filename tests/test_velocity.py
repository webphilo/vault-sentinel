from __future__ import annotations

from sentinel.models import Decision


def test_single_tx_cap(engine, make_req):
    v = engine.screen(make_req(amount=3_000_000, amount_usd=3_000_000))
    assert v.decision is Decision.BLOCK


def test_share_of_wallet_cap(engine, make_req):
    v = engine.screen(make_req(amount=200_000, amount_usd=200_000), wallet_balance_usd=1_000_000)
    assert v.decision is Decision.BLOCK


def test_sliding_window(engine, make_req):
    # 4 x $1.5M = $6M > $5M per 10 minutes
    decisions = [
        engine.screen(make_req(amount=1_500_000, amount_usd=1_500_000), wallet_balance_usd=500_000_000).decision
        for _ in range(4)
    ]
    assert Decision.BLOCK in decisions


def test_only_allowed_withdrawals_consume_the_window(engine, make_req):
    engine.screen(make_req(amount=1_900_000, amount_usd=1_900_000, tokens_in_tx=99))  # blocked
    v = engine.screen(make_req(amount=1_900_000, amount_usd=1_900_000), wallet_balance_usd=500_000_000)
    assert v.decision is not Decision.BLOCK or "window" not in " ".join(s.reason for s in v.signals)
