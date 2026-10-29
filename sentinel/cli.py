"""Command-line interface.

    sentinel serve                       run the API
    sentinel keygen                      create an Ed25519 attestation key pair
    sentinel gen-data data/history.csv   create synthetic training data
    sentinel train data/history.csv      train the AI anomaly model
    sentinel replay-incident             replay the 29 Oct 2026 outflow against your policy
    sentinel verify-audit                verify the audit log hash chain
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import get_settings, load_policy


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("sentinel.api:app_factory", factory=True, host=args.host, port=args.port,
                workers=args.workers, proxy_headers=True)


def cmd_keygen(_: argparse.Namespace) -> None:
    from .attestation import generate_keypair, key_id

    priv, pub = generate_keypair()
    print("# Keep the private key in your secret manager. Give the public key to the signer.")
    print(f"SENTINEL_SIGNING_KEY={priv}")
    print(f"SENTINEL_PUBLIC_KEY={pub}")
    print(f"# key_id={key_id(pub)}")


def cmd_gen_data(args: argparse.Namespace) -> None:
    from .simulate import generate_history, write_csv

    p = write_csv(generate_history(args.n, args.seed), args.out)
    print(f"Wrote {args.n} synthetic withdrawals to {p}")


def cmd_train(args: argparse.Namespace) -> None:
    from .anomaly_train import rows_from_csv
    from .detectors.anomaly import AnomalyDetector
    from .state import MemoryStore

    det = AnomalyDetector(load_policy(args.policy), MemoryStore())
    n = det.train(rows_from_csv(args.csv), n_estimators=args.trees)
    print(f"Trained Isolation Forest on {n} withdrawals -> {det.model_path}")


def cmd_replay(args: argparse.Namespace) -> None:
    from .attestation import Attestor
    from .audit import AuditLog
    from .engine import SentinelEngine
    from .providers import AddressProfile, ProviderRegistry, StaticProvider
    from .simulate import ATTACKER, incident_scenario
    from .state import MemoryStore

    policy = load_policy(args.policy)
    provider = StaticProvider()
    provider.add(AddressProfile(address=ATTACKER, tx_count=0))
    engine = SentinelEngine(policy, ProviderRegistry(default=provider), MemoryStore(),
                            AuditLog(":memory:"), Attestor(None, 120))

    print(f"Replaying 29 Oct 2026 outflow against {args.policy or 'config/policy.yaml'}\n")
    for req, balance in incident_scenario():
        v = engine.screen(req, balance)
        print(f"[{v.decision.value:5}] {req.request_id}  ${req.amount_usd:>16,.0f}  "
              f"{req.source_wallet} -> {req.destination[:14]}…  risk={v.risk_score:.2f}"
              f"{'  🧨 BREAKER' if v.breaker_tripped else ''}")
        for s in v.signals:
            print(f"          · [{s.detector}] {s.reason}")
    print("\nFrozen:", ", ".join(engine.breaker.status()) or "none")


def cmd_verify_audit(args: argparse.Namespace) -> None:
    from .audit import AuditLog

    ok, broken = AuditLog(args.db or get_settings().audit_db).verify_chain()
    if ok:
        print("Audit chain intact ✓")
    else:
        print(f"Audit chain BROKEN at row {broken}")
        sys.exit(2)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="sentinel", description="VaultSentinel hot wallet firewall")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the API server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--workers", type=int, default=1,
                   help="use >1 only with SENTINEL_REDIS_URL so workers share state")
    s.set_defaults(fn=cmd_serve)

    k = sub.add_parser("keygen", help="generate an Ed25519 attestation key pair")
    k.set_defaults(fn=cmd_keygen)

    g = sub.add_parser("gen-data", help="generate synthetic withdrawal history")
    g.add_argument("out")
    g.add_argument("-n", type=int, default=20_000)
    g.add_argument("--seed", type=int, default=7)
    g.set_defaults(fn=cmd_gen_data)

    t = sub.add_parser("train", help="train the AI anomaly model")
    t.add_argument("csv")
    t.add_argument("--policy", default=None)
    t.add_argument("--trees", type=int, default=300)
    t.set_defaults(fn=cmd_train)

    r = sub.add_parser("replay-incident", help="replay the 29 Oct 2026 Binance outflow")
    r.add_argument("--policy", default=None)
    r.set_defaults(fn=cmd_replay)

    v = sub.add_parser("verify-audit", help="verify audit log integrity")
    v.add_argument("--db", default=None)
    v.set_defaults(fn=cmd_verify_audit)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
