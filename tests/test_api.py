from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentinel.api import create_app
from sentinel.config import Settings


@pytest.fixture
def client(engine):
    settings = Settings(api_key="svc", operator_keys={"op-a": "alice", "op-b": "bob"})
    with TestClient(create_app(settings, engine)) as c:
        yield c


def body(**kw):
    req = dict(request_id="api-1", chain="ethereum", asset="USDT", amount=100, amount_usd=100,
               source_wallet="0xhot1", destination="0x00000000000000000000000000000000000000aa",
               initiator="withdrawal-service")
    req.update(kw)
    return {"request": req, "wallet_balance_usd": 10_000_000}


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_screen_requires_key(client):
    assert client.post("/v1/screen", json=body()).status_code == 422
    assert client.post("/v1/screen", json=body(), headers={"X-API-Key": "nope"}).status_code == 401


def test_screen_allow(client):
    r = client.post("/v1/screen", json=body(), headers={"X-API-Key": "svc"})
    assert r.status_code == 200
    assert r.json()["decision"] == "ALLOW"


def test_operator_endpoints_reject_service_key(client):
    assert client.get("/v1/holds", headers={"X-API-Key": "svc"}).status_code == 401
    assert client.get("/v1/holds", headers={"X-API-Key": "op-a"}).status_code == 200


def test_breaker_trip_and_reset(client):
    client.post("/v1/breaker/trip", json={"wallet": "0xhot1"}, headers={"X-API-Key": "svc"})
    r = client.post("/v1/screen", json=body(request_id="api-2"), headers={"X-API-Key": "svc"})
    assert r.json()["decision"] == "BLOCK"
    client.post("/v1/breaker/reset", json={"wallet": "0xhot1"}, headers={"X-API-Key": "op-a"})
    r = client.post("/v1/breaker/reset", json={"wallet": "0xhot1"}, headers={"X-API-Key": "op-b"})
    assert r.json()["reset"] is True


def test_treasury(client):
    r = client.post("/v1/treasury", json={"hot_usd": 300, "cold_usd": 700}, headers={"X-API-Key": "svc"})
    assert r.json()["compliant"] is False
