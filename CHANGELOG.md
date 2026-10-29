# Changelog

## [1.0.0] — 2026-10-30

### Added
- Pre-signing screening API (`POST /v1/screen`) with ALLOW / HOLD / BLOCK decisions
- Detectors: address intelligence, velocity limits, behavioural rules, AI anomaly detection
- Ed25519-signed attestations for signers
- Circuit breaker with wallet-level and exchange-wide freeze, four-eyes unfreeze
- Manual review queue with multi-operator approval
- Tamper-evident hash-chained audit log
- Providers: EVM (Etherscan v2), Tron, Solana, Bitcoin
- Telegram, Slack and signed webhook alerts; stablecoin freeze-request drafts
- Hot / cold storage ratio monitor
- Operator web console, Prometheus metrics and alert rules
- Docker, docker-compose and Kubernetes manifests
- `sentinel replay-incident` replay of the 29 Oct 2026 outflow
