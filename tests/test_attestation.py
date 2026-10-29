from __future__ import annotations

import time

from sentinel.attestation import Attestor, generate_keypair, verify_attestation


def test_roundtrip(make_req):
    priv, pub = generate_keypair()
    a = Attestor(priv, ttl_sec=60)
    req = make_req()
    att = a.issue(req)
    assert verify_attestation(att, pub, req)


def test_rejects_tampered_destination(make_req):
    priv, pub = generate_keypair()
    req = make_req()
    att = Attestor(priv).issue(req)
    other = req.model_copy(update={"destination": "0xattacker"})
    assert not verify_attestation(att, pub, other)


def test_rejects_expired(make_req):
    priv, pub = generate_keypair()
    req = make_req()
    att = Attestor(priv, ttl_sec=1).issue(req)
    assert not verify_attestation(att, pub, req, now=time.time() + 10)


def test_rejects_wrong_key(make_req):
    priv, _ = generate_keypair()
    _, other_pub = generate_keypair()
    req = make_req()
    assert not verify_attestation(Attestor(priv).issue(req), other_pub, req)
