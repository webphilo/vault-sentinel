"""Python SDK for signing services.

    from sentinel.client import SentinelClient, WithdrawalBlocked

    client = SentinelClient("http://sentinel:8080", api_key="...", public_key="...")
    attestation = client.require_allow(request_dict, wallet_balance_usd=12_000_000)
    signature = mpc.sign(tx)   # only reached if the withdrawal was approved
"""
from __future__ import annotations

from typing import Any

import httpx

from .attestation import verify_attestation
from .models import Attestation, Decision, Verdict, WithdrawalRequest


class WithdrawalBlocked(Exception):
    def __init__(self, verdict: Verdict):
        self.verdict = verdict
        reasons = "; ".join(s.reason for s in verdict.signals)
        super().__init__(f"{verdict.decision.value} (risk {verdict.risk_score:.2f}): {reasons}")


class SentinelClient:
    def __init__(self, base_url: str, api_key: str, public_key: str | None = None,
                 timeout: float = 5.0, client: httpx.Client | None = None):
        self.http = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout,
                                           headers={"X-API-Key": api_key})
        self._public_key = public_key

    @property
    def public_key(self) -> str:
        if not self._public_key:
            # Pin the key in production instead of fetching it: a fetched key can be spoofed.
            self._public_key = self.http.get("/v1/public-key").json()["public_key"]
        return self._public_key

    def screen(self, request: WithdrawalRequest | dict[str, Any],
               wallet_balance_usd: float | None = None) -> Verdict:
        req = request if isinstance(request, WithdrawalRequest) else WithdrawalRequest(**request)
        r = self.http.post("/v1/screen", json={"request": req.model_dump(mode="json"),
                                               "wallet_balance_usd": wallet_balance_usd})
        r.raise_for_status()
        return Verdict(**r.json())

    def require_allow(self, request: WithdrawalRequest | dict[str, Any],
                      wallet_balance_usd: float | None = None) -> Attestation:
        """Screen and return a verified attestation, or raise WithdrawalBlocked.

        Any transport error also raises: the caller must treat it as BLOCK (fail-closed).
        """
        req = request if isinstance(request, WithdrawalRequest) else WithdrawalRequest(**request)
        verdict = self.screen(req, wallet_balance_usd)
        if verdict.decision is not Decision.ALLOW or verdict.attestation is None:
            raise WithdrawalBlocked(verdict)
        if not verify_attestation(verdict.attestation, self.public_key, req):
            raise WithdrawalBlocked(verdict.model_copy(update={"decision": Decision.BLOCK}))
        return verdict.attestation

    def trip_breaker(self, wallet: str, reason: str = "manual") -> dict:
        r = self.http.post("/v1/breaker/trip", json={"wallet": wallet, "reason": reason})
        r.raise_for_status()
        return r.json()

    def report_treasury(self, hot_usd: float, cold_usd: float) -> dict:
        r = self.http.post("/v1/treasury", json={"hot_usd": hot_usd, "cold_usd": cold_usd})
        r.raise_for_status()
        return r.json()
