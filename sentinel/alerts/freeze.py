"""Freeze-request drafts for stablecoin issuers.

Centrally issued stablecoins can be frozen by their issuer, but only while the
funds have not been swapped or bridged, so minutes matter. This module pre-fills
the request so the on-call engineer only has to send it through the issuer's
official compliance / law-enforcement channel.
"""
from __future__ import annotations

from ..models import WithdrawalRequest

FREEZABLE = {
    "USDT": "Tether",
    "USDC": "Circle",
    "EURC": "Circle",
    "PYUSD": "Paxos",
    "USDP": "Paxos",
    "FDUSD": "First Digital",
    "TUSD": "Techteryx",
}


def freeze_request_draft(req: WithdrawalRequest, exchange_name: str = "<EXCHANGE>",
                         tx_hash: str | None = None) -> dict | None:
    issuer = FREEZABLE.get(req.asset.upper())
    if not issuer:
        return None
    body = f"""Subject: URGENT — freeze request, suspected hot wallet compromise at {exchange_name}

To the {issuer} compliance team,

{exchange_name} is responding to a suspected compromise of one of its hot wallets.
We request an immediate freeze of the destination address below.

Chain:                {req.chain}
Asset:                {req.asset}
Amount:               {req.amount:,.2f}
Source (our wallet):  {req.source_wallet}
Destination:          {req.destination}
Transaction hash:     {tx_hash or '<TX_HASH>'}
Time (UTC):           {req.created_at.isoformat()}
Internal reference:   {req.request_id}

A formal law-enforcement referral will follow. Contact: <ON-CALL NAME, PHONE>.
"""
    return {"issuer": issuer, "asset": req.asset.upper(), "draft": body}
