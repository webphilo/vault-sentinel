"""How a signing service should integrate VaultSentinel.

The signer is the last line of defence: it refuses to sign unless it holds a
fresh, valid attestation that covers exactly this transaction.
"""
from __future__ import annotations

import os

import httpx

from sentinel.client import SentinelClient, WithdrawalBlocked

client = SentinelClient(
    base_url=os.getenv("SENTINEL_URL", "http://localhost:8080"),
    api_key=os.environ["SENTINEL_API_KEY"],
    public_key=os.environ["SENTINEL_PUBLIC_KEY"],  # pinned, never fetched at runtime
)


def sign_with_mpc(tx: dict) -> str:  # placeholder for your MPC / HSM call
    raise NotImplementedError


def process_withdrawal(tx: dict, hot_wallet_balance_usd: float) -> str:
    request = {
        "request_id": tx["id"],
        "chain": tx["chain"],
        "asset": tx["asset"],
        "amount": tx["amount"],
        "amount_usd": tx["amount_usd"],
        "source_wallet": tx["from"],
        "destination": tx["to"],
        "initiator": "withdrawal-service",
        "user_id": tx.get("user_id"),
        "tokens_in_tx": len(tx.get("assets", [tx["asset"]])),
    }
    try:
        attestation = client.require_allow(request, wallet_balance_usd=hot_wallet_balance_usd)
    except WithdrawalBlocked as exc:
        # HOLD or BLOCK: do not sign. HOLD will be approved or rejected in the console.
        print(f"withdrawal {tx['id']} not signed: {exc}")
        raise
    except httpx.HTTPError:
        # Sentinel unreachable -> fail closed.
        print(f"withdrawal {tx['id']} not signed: sentinel unavailable")
        raise

    tx["sentinel_attestation"] = attestation.model_dump()
    return sign_with_mpc(tx)
