"""Decision engine: runs every detector and turns their signals into one verdict."""
from __future__ import annotations

import logging
import time

from .attestation import Attestor
from .audit import AuditLog
from .breaker import CircuitBreaker
from .detectors import (
    AddressIntelDetector,
    AnomalyDetector,
    BehaviorDetector,
    Context,
    Detector,
    VelocityDetector,
)
from .holds import HoldQueue
from .metrics import (
    BREAKER_TRIPPED,
    DECISIONS,
    HOLDS_PENDING,
    LATENCY,
    SIGNALS,
    USD_ALLOWED,
    USD_BLOCKED,
)
from .models import Decision, Signal, Verdict, WithdrawalRequest
from .providers import AddressProfile, ProviderRegistry
from .state import StateStore

log = logging.getLogger("sentinel.engine")


def combine(signals: list[Signal]) -> float:
    """Probability that at least one independent signal is a true positive."""
    keep = 1.0
    for s in signals:
        keep *= 1.0 - s.score
    return round(1.0 - keep, 4)


class SentinelEngine:
    def __init__(
        self,
        policy: dict,
        providers: ProviderRegistry,
        store: StateStore,
        audit: AuditLog | None = None,
        attestor: Attestor | None = None,
    ):
        self.policy = policy
        self.providers = providers
        self.store = store
        self.audit = audit
        self.attestor = attestor or Attestor(None, int(policy["attestation"]["ttl_sec"]))

        self.address_intel = AddressIntelDetector(policy)
        self.velocity = VelocityDetector(policy, store)
        self.behavior = BehaviorDetector(policy, store)
        self.anomaly = AnomalyDetector(policy, store)
        self.detectors: list[Detector] = [self.address_intel, self.velocity, self.behavior, self.anomaly]

        self.breaker = CircuitBreaker(policy, store)
        self.holds = HoldQueue(policy, store)

        d = policy["decision"]
        self.hold_threshold = float(d["hold_threshold"])
        self.block_threshold = float(d["block_threshold"])
        self.detector_error_score = float(d.get("detector_error_score", 0.6))

    # ------------------------------------------------------------------ helpers
    def _profile(self, req: WithdrawalRequest) -> AddressProfile:
        if self.address_intel.is_allowlisted(req.destination):
            return AddressProfile(address=req.destination, tx_count=1)
        try:
            return self.providers.get(req.chain).profile(req.destination)
        except Exception:
            log.exception("provider failure for %s", req.chain)
            return AddressProfile(address=req.destination, available=False)

    def _run_detectors(self, ctx: Context, only: list[Detector] | None = None) -> list[Signal]:
        signals: list[Signal] = []
        for det in only or self.detectors:
            try:
                signals += det.evaluate(ctx)
            except Exception:
                log.exception("detector %s failed", det.name)
                signals.append(Signal(detector=det.name, score=self.detector_error_score,
                                      reason="Detector error (fail-closed)"))
        return signals

    def _decide(self, signals: list[Signal]) -> tuple[Decision, float]:
        risk = combine(signals)
        if any(s.hard_block for s in signals) or risk >= self.block_threshold:
            return Decision.BLOCK, risk
        if risk >= self.hold_threshold:
            return Decision.HOLD, risk
        return Decision.ALLOW, risk

    def _allowed(self, ctx: Context) -> None:
        for det in self.detectors:
            try:
                det.on_allowed(ctx)
            except Exception:
                log.exception("on_allowed failed in %s", det.name)
        USD_ALLOWED.labels(ctx.request.chain).inc(ctx.request.amount_usd)

    def _record(self, req: WithdrawalRequest, v: Verdict, event: str = "screen", actor: str | None = None) -> None:
        DECISIONS.labels(v.decision.value, req.chain).inc()
        for s in v.signals:
            SIGNALS.labels(s.detector, str(s.hard_block).lower()).inc()
        if v.decision is Decision.BLOCK:
            USD_BLOCKED.labels(req.chain).inc(req.amount_usd)
        BREAKER_TRIPPED.set(len(self.breaker.status()))
        HOLDS_PENDING.set(len(self.holds.list()))
        if self.audit:
            self.audit.append(
                event,
                {"request": req.model_dump(mode="json"), "verdict": v.model_dump(mode="json")},
                request_id=req.request_id, decision=v.decision.value, risk=v.risk_score,
                actor=actor or req.initiator,
            )

    # ------------------------------------------------------------------ public
    def screen(self, req: WithdrawalRequest, wallet_balance_usd: float | None = None) -> Verdict:
        t0 = time.perf_counter()
        now = time.time()

        if self.breaker.is_tripped(req.source_wallet):
            v = Verdict(
                request_id=req.request_id, decision=Decision.BLOCK, risk_score=1.0, breaker_tripped=True,
                signals=[Signal(detector="circuit_breaker", score=1.0, hard_block=True,
                                reason="Wallet is frozen by the circuit breaker")],
            )
        else:
            ctx = Context(request=req, wallet_balance_usd=wallet_balance_usd,
                          profile=self._profile(req), now=now)
            signals = self._run_detectors(ctx)
            decision, risk = self._decide(signals)
            v = Verdict(request_id=req.request_id, decision=decision, risk_score=risk, signals=signals)

            if decision is Decision.BLOCK:
                v.breaker_tripped = self.breaker.record_hard_block(req.source_wallet)
            elif decision is Decision.ALLOW:
                self._allowed(ctx)
                v.attestation = self.attestor.issue(req)
            else:
                self.holds.add(req, wallet_balance_usd, v)

        v.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        LATENCY.observe(v.latency_ms / 1000)
        self._record(req, v)
        return v

    def approve_hold(self, request_id: str, operator: str) -> Verdict | None:
        """Add an operator approval. Returns the final verdict once fully approved, else None.

        Raises KeyError if the hold does not exist or has expired.
        """
        item, done = self.holds.approve(request_id, operator)
        if item is None:
            raise KeyError(request_id)
        if not done:
            return None

        req = WithdrawalRequest(**item["request"])
        ctx = Context(request=req, wallet_balance_usd=item.get("wallet_balance_usd"), profile=None, now=time.time())

        # Re-check what may have changed while the request was parked.
        if self.breaker.is_tripped(req.source_wallet):
            signals = [Signal(detector="circuit_breaker", score=1.0, hard_block=True,
                              reason="Wallet was frozen while the request was on hold")]
        else:
            signals = [s for s in self._run_detectors(ctx, [self.velocity]) if s.hard_block]

        if signals:
            v = Verdict(request_id=req.request_id, decision=Decision.BLOCK, risk_score=1.0, signals=signals)
        else:
            self._allowed(ctx)
            v = Verdict(
                request_id=req.request_id, decision=Decision.ALLOW, risk_score=float(item["verdict"]["risk_score"]),
                signals=[Signal(detector="manual_review", score=0.0,
                                reason=f"Approved by {', '.join(item['approvals'])}")],
                attestation=self.attestor.issue(req),
            )
        self._record(req, v, event="hold_approved", actor=",".join(item["approvals"]))
        return v

    def reject_hold(self, request_id: str, operator: str) -> bool:
        ok = self.holds.reject(request_id)
        if ok and self.audit:
            self.audit.append("hold_rejected", {"request_id": request_id}, request_id=request_id,
                              decision="BLOCK", actor=operator)
        return ok
