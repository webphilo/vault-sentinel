"""Destination address intelligence.

Large hot wallet drains almost always pay out to addresses that were created
minutes or hours earlier, and attacker infrastructure is typically funded through
mixers to break attribution. Both properties are observable before signing.
"""
from __future__ import annotations

from ..config import load_list
from ..models import Signal
from .base import Context, Detector


class AddressIntelDetector(Detector):
    name = "address_intel"

    def __init__(self, policy: dict):
        cfg = policy["address_intel"]
        self.min_age_hours = float(cfg["min_address_age_hours"])
        self.new_address_score = float(cfg.get("new_address_score", 0.7))
        self.unavailable_score = float(cfg.get("unavailable_score", 0.55))
        self.mixers = {a.lower() for a in cfg.get("mixer_addresses", [])} | load_list(
            policy, cfg.get("mixer_list_file")
        )
        self.denylist = {a.lower() for a in cfg.get("denylist", [])} | load_list(policy, cfg.get("denylist_file"))
        self.allowlist = {a.lower() for a in cfg.get("allowlist", [])} | load_list(policy, cfg.get("allowlist_file"))

    def is_allowlisted(self, address: str) -> bool:
        return address.lower() in self.allowlist

    def evaluate(self, ctx: Context) -> list[Signal]:
        if ctx.dest in self.allowlist:
            return []
        if ctx.dest in self.denylist:
            return [self.signal(1.0, "Destination is on the denylist", hard=True)]
        if ctx.dest in self.mixers:
            return [self.signal(1.0, "Destination is a known mixer contract", hard=True)]

        prof = ctx.profile
        if prof is None or not prof.available:
            return [self.signal(self.unavailable_score,
                                "On-chain data unavailable for destination (fail-closed)")]

        out: list[Signal] = []
        if prof.is_new:
            out.append(self.signal(self.new_address_score, "Destination has no on-chain history (fresh address)"))
        else:
            age = ctx.dest_age_hours
            if age is not None and age < self.min_age_hours:
                # younger -> riskier, linear from new_address_score down to 0.2
                score = 0.2 + (self.new_address_score - 0.2) * (1 - age / self.min_age_hours)
                out.append(self.signal(score, f"Destination first seen {age:.1f}h ago"))

        if any(f in self.mixers for f in prof.funded_by) or "mixer" in prof.labels:
            out.append(self.signal(1.0, "Destination was funded through a mixer (e.g. Tornado Cash)", hard=True))
        if any(f in self.denylist for f in prof.funded_by):
            out.append(self.signal(1.0, "Destination was funded by a denylisted address", hard=True))
        if "sanctioned" in prof.labels:
            out.append(self.signal(1.0, "Destination is sanctioned", hard=True))
        return out
