# Security Policy

## Reporting a vulnerability

Please **do not open a public issue**. Report privately through
[GitHub Security Advisories](../../security/advisories/new). We aim to acknowledge within 72 hours.

## Hardening checklist

- Run VaultSentinel on an internal network only; never expose it to the internet.
- Make it a **mandatory co-signer** of your MPC / multisig setup, not just an advisory service.
- Pin `SENTINEL_PUBLIC_KEY` in the signer; never fetch it at runtime.
- Store `SENTINEL_SIGNING_KEY`, API keys and operator keys in a secret manager and rotate them.
- Require two reviewers for any change to `config/policy.yaml` (see `.github/CODEOWNERS`).
- Ship the audit log to write-once storage and run `sentinel verify-audit` on a schedule.
- Treat VaultSentinel being unreachable as BLOCK in the signer (fail-closed).
