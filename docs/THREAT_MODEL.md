# Threat model

| Threat | Mitigation | Residual risk |
|---|---|---|
| Compromised withdrawal service creates malicious withdrawals | Trusted-initiator list, velocity caps, address intel, AI anomaly, attestation required by signer | Small withdrawals under every threshold to aged addresses |
| Attacker drains wallet in one batch tx | `max_tokens_per_tx`, `max_single_tx_usd`, `max_share_of_wallet_per_tx` | — |
| Slow drain across many small txs | Sliding windows per wallet and exchange-wide, online baseline | Drain below window limits until detected by humans |
| Fresh attacker addresses | Address age, mixer-funding check, fan-in rule | Pre-aged attacker addresses |
| Coordinated multi-wallet drain | Exchange-wide circuit breaker | First blocked tx per wallet is still evaluated individually |
| Replay of an old approval | Attestation bound to tx fields, 2-minute expiry, unique `request_id` | Signer must track used `request_id`s |
| Signer bypasses Sentinel | Make Sentinel an MPC co-signer / HSM policy | Not mitigated if keys are exfiltrated outright |
| Insider unfreezes wallets alone | Unfreeze and hold approval require two distinct operators | Two colluding operators |
| Audit log tampering | SHA-256 hash chain, `verify-audit`, WORM shipping | Deletion of the whole database (detect by shipping) |
| Indexer outage or poisoning | Fail-closed, several providers, TTL cache only for successful lookups | Wrong data from a compromised indexer |
| Policy weakened via config change | CODEOWNERS, two reviewers, audit of deployments | — |
