# Attack scenarios and detection coverage

This document describes the hot wallet attack patterns VaultSentinel is designed to stop, the
observable signals each pattern produces before a transaction is signed, and the control that acts on them.

## 1. Rapid multi-wallet drain

**Pattern.** The attacker gains the ability to produce valid signatures (compromised withdrawal
service, signing infrastructure or operator credentials) and empties as many hot wallets as possible
before the exchange reacts. Typical characteristics:

- one or more batch transactions sweeping dozens of assets at once;
- amounts that are orders of magnitude above normal withdrawals and close to the full wallet balance;
- a destination address created shortly before the attack;
- attacker gas funded through a mixer to break attribution;
- several hot wallets paying the same destination within seconds or minutes;
- withdrawal requests created by an identity that never creates withdrawals.

**Controls.**

| Signal | Control | Effect |
|---|---|---|
| Fresh destination | `address_intel.min_address_age_hours` | +0.70 risk |
| Mixer-funded destination | `address_intel` + `config/lists/mixers.txt` | BLOCK |
| Batch sweep | `velocity.max_tokens_per_tx` | BLOCK |
| Oversized transaction | `velocity.max_single_tx_usd`, `per_asset_max_single_tx_usd` | BLOCK |
| Most of the wallet in one transaction | `velocity.max_share_of_wallet_per_tx` | BLOCK |
| Unknown initiator | `behavior.trusted_initiators` | BLOCK |
| Several wallets paying one address | `behavior.fan_in_max_source_wallets` | BLOCK |
| Blocks on several wallets | `circuit_breaker.global_trip_after_wallets` | All hot wallets frozen |
| Stablecoins in flight | `alerts.freeze` | Issuer freeze request drafted |

**Bounded loss.** With the default policy the first malicious transaction is rejected outright. Even
if an attacker shapes transactions to pass every per-transaction rule, the exchange-wide window caps
the loss at `global_windows[0].max_usd` (15M USD per 10 minutes by default) before the circuit breaker
and on-call staff take over.

Simulate it against your policy:

```bash
sentinel simulate-drain
```

## 2. Slow drain

**Pattern.** Many withdrawals that each look ordinary, spread over hours, to aged addresses.

**Controls.** Sliding windows per wallet and exchange-wide; the online per-wallet baseline (z-score on
log amount); the Isolation Forest model, which scores the combination of amount, time of day, weekday,
destination age and share of wallet rather than any single threshold.

## 3. Compromised withdrawal service

**Pattern.** The attacker controls the service that creates withdrawal requests and can choose every field.

**Controls.** The signer only signs with a valid Ed25519 attestation bound to the exact chain, asset,
amount, source and destination, valid for two minutes. A service that bypasses VaultSentinel never
obtains one. Initiator allow-listing and velocity limits apply to everything the service submits.

## 4. Insider abuse

**Pattern.** A single operator approves a malicious held withdrawal or unfreezes a wallet during an attack.

**Controls.** Held withdrawals and breaker resets require approvals from distinct operators
(`holds.approvals_required`, `circuit_breaker.reset_requires_approvals`). Every action is written to a
hash-chained audit log with the operator identity derived from their API key, not from user input.

## 5. Infrastructure degradation

**Pattern.** The attacker or an outage makes the chain indexer unavailable, hoping checks fail open.

**Controls.** Fail-closed defaults: unavailable data raises risk to HOLD; a crashing detector adds risk;
an unknown chain has no provider and is held; an unreachable VaultSentinel means no attestation and
therefore no signature.

## Out of scope

VaultSentinel protects the signing path. If private key material is exfiltrated and used outside the
exchange's infrastructure, no pre-signing control can observe it. Deploy VaultSentinel as a mandatory
co-signer in an MPC or multisig scheme so that a valid signature cannot exist without its approval
(see [INTEGRATION.md](INTEGRATION.md) and [THREAT_MODEL.md](THREAT_MODEL.md)).
