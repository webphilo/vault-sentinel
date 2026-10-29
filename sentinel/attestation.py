"""Signed approvals (Ed25519).

VaultSentinel signs every ALLOW decision. The signing service (MPC node, HSM
policy engine, multisig co-signer) verifies the attestation and the exact
transaction fields BEFORE producing a signature. A withdrawal that bypassed
screening has no valid attestation and is refused by the signer.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .models import Attestation, WithdrawalRequest

log = logging.getLogger("sentinel.attestation")

BOUND_FIELDS = ("request_id", "chain", "asset", "amount", "source_wallet", "destination")


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _amount(v: float) -> str:
    return format(v, ".18g")


def generate_keypair() -> tuple[str, str]:
    key = Ed25519PrivateKey.generate()
    priv = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return _b64(priv), _b64(pub)


def key_id(public_b64: str) -> str:
    return hashlib.sha256(base64.b64decode(public_b64)).hexdigest()[:16]


class Attestor:
    def __init__(self, private_key_b64: Optional[str], ttl_sec: int = 120):
        if private_key_b64:
            self._key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
        else:
            log.warning("SENTINEL_SIGNING_KEY not set: using an ephemeral key (attestations break on restart)")
            self._key = Ed25519PrivateKey.generate()
        pub = self._key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.public_key_b64 = _b64(pub)
        self.key_id = key_id(self.public_key_b64)
        self.ttl = ttl_sec

    def issue(self, req: WithdrawalRequest, decision: str = "ALLOW") -> Attestation:
        now = int(time.time())
        payload = {
            "v": 1,
            "request_id": req.request_id,
            "chain": req.chain,
            "asset": req.asset,
            "amount": _amount(req.amount),
            "source_wallet": req.source_wallet.lower(),
            "destination": req.destination.lower(),
            "decision": decision,
            "iat": now,
            "exp": now + self.ttl,
            "kid": self.key_id,
        }
        sig = self._key.sign(canonical(payload))
        return Attestation(payload=payload, signature=_b64(sig), key_id=self.key_id)


def verify_attestation(
    att: Attestation | dict,
    public_key_b64: str,
    req: Optional[WithdrawalRequest | dict] = None,
    now: Optional[float] = None,
) -> bool:
    """Verify signature, expiry, decision and (optionally) that it covers exactly this transaction."""
    if isinstance(att, dict):
        att = Attestation(**att)
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        pub.verify(base64.b64decode(att.signature), canonical(att.payload))
    except (InvalidSignature, ValueError):
        return False

    p = att.payload
    if p.get("decision") != "ALLOW":
        return False
    if (now or time.time()) > float(p.get("exp", 0)):
        return False
    if req is not None:
        r = req.model_dump() if isinstance(req, WithdrawalRequest) else dict(req)
        expected = {
            "request_id": r["request_id"],
            "chain": str(r["chain"]).lower(),
            "asset": r["asset"],
            "amount": _amount(float(r["amount"])),
            "source_wallet": str(r["source_wallet"]).lower(),
            "destination": str(r["destination"]).lower(),
        }
        if any(p.get(k) != v for k, v in expected.items()):
            return False
    return True
