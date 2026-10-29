# Integration guide

## 1. Generate the attestation key

```bash
sentinel keygen
# SENTINEL_SIGNING_KEY=...   -> VaultSentinel secret
# SENTINEL_PUBLIC_KEY=...    -> pinned in every signer
```

## 2. Call VaultSentinel before every signature

```python
from sentinel.client import SentinelClient, WithdrawalBlocked

client = SentinelClient(url, api_key=SERVICE_KEY, public_key=PINNED_PUBLIC_KEY)
attestation = client.require_allow(request, wallet_balance_usd=balance)  # raises if not ALLOW
```

Full example: [`examples/signer_integration.py`](../examples/signer_integration.py).

## 3. Enforce it inside the signer

The real protection comes from the signer refusing to sign without a valid attestation:

```python
from sentinel.attestation import verify_attestation

if not verify_attestation(attestation, PINNED_PUBLIC_KEY, request):
    raise PermissionError("no valid VaultSentinel approval")
```

`verify_attestation` checks the Ed25519 signature, the 2-minute expiry, `decision == ALLOW` and that
`request_id`, `chain`, `asset`, `amount`, `source_wallet`, `destination` match the transaction byte for byte.

**Recommended:** run the check inside one MPC party / the HSM policy module, so a compromised
withdrawal service cannot skip it.

## 4. Report treasury balances

```bash
curl -X POST $SENTINEL/v1/treasury -H "X-API-Key: $KEY" \
  -d '{"hot_usd": 120000000, "cold_usd": 980000000}'
```

## 5. Train the AI model on your history

Export past withdrawals to CSV (`amount_usd, created_at, tokens_in_tx, dest_age_hours, wallet_share`):

```bash
sentinel train exports/withdrawals_90d.csv
```

Restart the service to load the model. Retrain weekly.

## 6. Operators

Open `http://<sentinel>:8080/` and log in with an operator key to approve or reject held withdrawals,
freeze wallets and vote to unfreeze them.
