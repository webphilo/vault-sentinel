"""REST API.

The signing service MUST call POST /v1/screen before every signature and sign
ONLY when decision == ALLOW and the returned attestation verifies.
"""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import __version__
from .alerts import Notifier, freeze_request_draft
from .config import Settings, get_settings
from .engine import SentinelEngine
from .factory import build_engine
from .logging_setup import setup_logging
from .models import Decision, TreasuryReport, Verdict, WithdrawalRequest
from .treasury import TreasuryMonitor

DASHBOARD = Path(__file__).resolve().parent / "dashboard" / "index.html"


# --------------------------------------------------------------------------- schemas
class ScreenBody(BaseModel):
    request: WithdrawalRequest
    wallet_balance_usd: Optional[float] = Field(None, ge=0)


class WalletBody(BaseModel):
    wallet: str
    reason: str = "manual"


class FreezeBody(BaseModel):
    request: WithdrawalRequest
    exchange_name: str = "<EXCHANGE>"
    tx_hash: Optional[str] = None


# --------------------------------------------------------------------------- auth
def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _engine(request: Request) -> SentinelEngine:
    return request.app.state.engine


def require_service(request: Request, x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    s = _settings(request)
    if s.api_key and hmac.compare_digest(x_api_key, s.api_key):
        return "service"
    raise HTTPException(status_code=401, detail="invalid service api key")


def require_operator(request: Request, x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    s = _settings(request)
    for key, name in s.operator_keys.items():
        if hmac.compare_digest(x_api_key, key):
            return name
    raise HTTPException(status_code=401, detail="invalid operator api key")


def require_any(request: Request, x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    try:
        return require_operator(request, x_api_key)
    except HTTPException:
        return require_service(request, x_api_key)


# --------------------------------------------------------------------------- app
def create_app(settings: Optional[Settings] = None, engine: Optional[SentinelEngine] = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.log_level)
        app.state.settings = settings
        app.state.engine = engine or build_engine(settings)
        app.state.notifier = Notifier(settings)
        app.state.treasury = TreasuryMonitor(app.state.engine.policy)
        yield

    app = FastAPI(
        title="VaultSentinel",
        version=__version__,
        description="AI-powered pre-signing firewall for crypto exchange hot wallets",
        lifespan=lifespan,
    )

    # ---------------------------------------------------------------- public
    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(DASHBOARD)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/ready", tags=["system"])
    def ready(request: Request) -> dict:
        eng = _engine(request)
        return {
            "status": "ready",
            "chains": eng.providers.chains,
            "ai_model_trained": eng.anomaly.trained,
            "breaker_tripped": list(eng.breaker.status()),
        }

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/public-key", tags=["attestation"])
    def public_key(request: Request) -> dict:
        a = _engine(request).attestor
        return {"algorithm": "Ed25519", "key_id": a.key_id, "public_key": a.public_key_b64}

    # ---------------------------------------------------------------- service
    @app.post("/v1/screen", response_model=Verdict, tags=["screening"])
    def screen(body: ScreenBody, request: Request, tasks: BackgroundTasks,
               _: str = Depends(require_service)) -> Verdict:
        verdict = _engine(request).screen(body.request, body.wallet_balance_usd)
        if verdict.decision is not Decision.ALLOW:
            tasks.add_task(request.app.state.notifier.verdict, body.request, verdict)
        return verdict

    @app.post("/v1/treasury", tags=["treasury"])
    async def treasury(body: TreasuryReport, request: Request, _: str = Depends(require_any)) -> dict:
        result = request.app.state.treasury.check(body.hot_usd, body.cold_usd)
        if not result["compliant"]:
            await request.app.state.notifier.send("[VaultSentinel] TREASURY ALERT\n" + "\n".join(result["issues"]))
        return result

    # ---------------------------------------------------------------- operators
    @app.get("/v1/holds", tags=["review"])
    def holds(request: Request, _: str = Depends(require_operator)) -> dict:
        return {"holds": _engine(request).holds.list()}

    @app.post("/v1/holds/{request_id}/approve", tags=["review"])
    def approve(request_id: str, request: Request, operator: str = Depends(require_operator)) -> dict:
        try:
            v = _engine(request).approve_hold(request_id, operator)
        except KeyError:
            raise HTTPException(status_code=404, detail="hold not found or expired")
        if v is None:
            return {"status": "pending", "approved_by": operator}
        return {"status": "final", "verdict": v.model_dump(mode="json")}

    @app.post("/v1/holds/{request_id}/reject", tags=["review"])
    def reject(request_id: str, request: Request, operator: str = Depends(require_operator)) -> dict:
        if not _engine(request).reject_hold(request_id, operator):
            raise HTTPException(status_code=404, detail="hold not found or expired")
        return {"status": "rejected", "by": operator}

    @app.get("/v1/breaker", tags=["circuit breaker"])
    def breaker(request: Request, _: str = Depends(require_any)) -> dict:
        return {"tripped": _engine(request).breaker.status()}

    @app.post("/v1/breaker/trip", tags=["circuit breaker"])
    async def breaker_trip(body: WalletBody, request: Request, who: str = Depends(require_any)) -> dict:
        eng = _engine(request)
        eng.breaker.trip(body.wallet, f"{body.reason} (by {who})")
        if eng.audit:
            eng.audit.append("breaker_trip", body.model_dump(), actor=who)
        await request.app.state.notifier.send(f"[VaultSentinel] CIRCUIT BREAKER tripped for {body.wallet} by {who}: {body.reason}")
        return {"tripped": True, "wallet": body.wallet.lower()}

    @app.post("/v1/breaker/reset", tags=["circuit breaker"])
    def breaker_reset(body: WalletBody, request: Request, operator: str = Depends(require_operator)) -> dict:
        eng = _engine(request)
        done = eng.breaker.approve_reset(body.wallet, operator)
        if eng.audit:
            eng.audit.append("breaker_reset_vote", {"wallet": body.wallet, "done": done}, actor=operator)
        return {"reset": done, "wallet": body.wallet.lower()}

    @app.post("/v1/freeze-draft", tags=["incident"])
    def freeze_draft(body: FreezeBody, _: str = Depends(require_operator)) -> dict:
        draft = freeze_request_draft(body.request, body.exchange_name, body.tx_hash)
        if draft is None:
            raise HTTPException(status_code=422, detail="asset has no known freezing issuer")
        return draft

    @app.get("/v1/audit", tags=["audit"])
    def audit(request: Request, limit: int = Query(100, le=1000), decision: Optional[Decision] = None,
              _: str = Depends(require_operator)) -> dict:
        eng = _engine(request)
        if not eng.audit:
            return {"events": []}
        return {"events": eng.audit.recent(limit, decision.value if decision else None)}

    @app.get("/v1/audit/verify", tags=["audit"])
    def audit_verify(request: Request, _: str = Depends(require_operator)) -> dict:
        eng = _engine(request)
        if not eng.audit:
            return {"ok": True, "broken_at": None}
        ok, broken = eng.audit.verify_chain()
        return {"ok": ok, "broken_at": broken}

    @app.get("/v1/stats", tags=["audit"])
    def stats(request: Request, hours: int = Query(24, ge=1, le=24 * 90),
              _: str = Depends(require_operator)) -> dict:
        eng = _engine(request)
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return {
            "window_hours": hours,
            "decisions": eng.audit.stats(since) if eng.audit else {},
            "holds_pending": len(eng.holds.list()),
            "breaker": eng.breaker.status(),
            "ai_model_trained": eng.anomaly.trained,
        }

    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn --factory sentinel.api:app_factory`."""
    return create_app()
