"""Telegram, Slack and generic signed webhooks."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

import httpx

from ..config import Settings
from ..models import Verdict, WithdrawalRequest

log = logging.getLogger("sentinel.alerts")

def format_verdict(req: WithdrawalRequest, v: Verdict) -> str:
    reasons = "\n".join(f"- [{s.detector}] {s.reason}" for s in v.signals) or "- no signals"
    breaker = "\nCIRCUIT BREAKER TRIPPED" if v.breaker_tripped else ""
    return (
        f"[VaultSentinel] {v.decision.value} risk={v.risk_score:.2f}{breaker}\n"
        f"Request: {req.request_id} by {req.initiator}\n"
        f"{req.amount:,.6g} {req.asset} (${req.amount_usd:,.0f}) on {req.chain}\n"
        f"From: {req.source_wallet}\nTo:   {req.destination}\n{reasons}"
    )


class Notifier:
    def __init__(self, settings: Settings):
        self.s = settings

    @property
    def enabled(self) -> bool:
        s = self.s
        return bool((s.telegram_bot_token and s.telegram_chat_id) or s.slack_webhook_url or s.webhook_url)

    async def send(self, text: str, event: Optional[dict[str, Any]] = None) -> None:
        log.warning(text.replace("\n", " | "))
        if not self.enabled:
            return
        async with httpx.AsyncClient(timeout=5.0) as client:
            if self.s.telegram_bot_token and self.s.telegram_chat_id:
                await self._post(client, f"https://api.telegram.org/bot{self.s.telegram_bot_token}/sendMessage",
                                 {"chat_id": self.s.telegram_chat_id, "text": text}, "telegram")
            if self.s.slack_webhook_url:
                await self._post(client, self.s.slack_webhook_url, {"text": text}, "slack")
            if self.s.webhook_url:
                body = json.dumps(event or {"text": text}, default=str).encode()
                headers = {"Content-Type": "application/json"}
                if self.s.webhook_secret:
                    sig = hmac.new(self.s.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
                    headers["X-Sentinel-Signature"] = f"sha256={sig}"
                try:
                    await client.post(self.s.webhook_url, content=body, headers=headers)
                except httpx.HTTPError as exc:
                    log.error("webhook alert failed: %s", exc)

    async def _post(self, client: httpx.AsyncClient, url: str, payload: dict, channel: str) -> None:
        try:
            r = await client.post(url, json=payload)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("%s alert failed: %s", channel, exc)

    async def verdict(self, req: WithdrawalRequest, v: Verdict) -> None:
        await self.send(format_verdict(req, v), {
            "type": "verdict",
            "request": req.model_dump(mode="json"),
            "verdict": v.model_dump(mode="json"),
        })
