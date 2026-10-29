"""Core data models."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Decision(str, Enum):
    ALLOW = "ALLOW"  # safe to sign
    HOLD = "HOLD"    # park the request, require human approval (four-eyes)
    BLOCK = "BLOCK"  # reject and raise an alarm


class WithdrawalRequest(BaseModel):
    """A withdrawal that must be screened BEFORE the transaction is signed."""

    request_id: str = Field(..., min_length=1, max_length=128)
    chain: str = Field(..., examples=["ethereum"])
    asset: str = Field(..., examples=["USDT"])
    amount: float = Field(..., gt=0)
    amount_usd: float = Field(..., ge=0)
    source_wallet: str = Field(..., description="Exchange hot wallet that will sign")
    destination: str
    initiator: str = Field(..., description="Service or operator that created the request")
    user_id: Optional[str] = None
    tokens_in_tx: int = Field(1, ge=1, description="Distinct assets moved by this tx (batch/multicall)")
    memo: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("chain", "asset")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip()

    @field_validator("chain")
    @classmethod
    def _lower_chain(cls, v: str) -> str:
        return v.lower()

    @field_validator("created_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


class Signal(BaseModel):
    """A single risk signal produced by one detector."""

    detector: str
    score: float = Field(..., ge=0, le=1)
    reason: str
    hard_block: bool = False


class Attestation(BaseModel):
    """Ed25519-signed approval. The signer must verify it before signing."""

    payload: dict[str, Any]
    signature: str
    key_id: str


class Verdict(BaseModel):
    request_id: str
    decision: Decision
    risk_score: float
    signals: list[Signal]
    breaker_tripped: bool = False
    attestation: Optional[Attestation] = None
    latency_ms: float = 0.0
    evaluated_at: datetime = Field(default_factory=utcnow)


class TreasuryReport(BaseModel):
    hot_usd: float = Field(..., ge=0)
    cold_usd: float = Field(..., ge=0)
