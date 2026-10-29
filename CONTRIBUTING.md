# Contributing

1. Fork and create a branch: `git checkout -b feature/my-detector`
2. `make dev` installs dependencies and pre-commit hooks.
3. A new detector subclasses `sentinel.detectors.base.Detector` and returns `list[Signal]`.
   Register it in `sentinel/engine.py` and add its parameters to `config/policy.yaml`.
4. Keep the system **fail-closed**: an error must raise risk, never lower it.
5. Describe in the PR which attack scenario the change addresses.

Most wanted: XRP / TON / Cosmos providers, Chainalysis / TRM / Arkham label feeds,
graph-based clustering of attacker addresses, a co-signer plug-in for popular MPC stacks.
