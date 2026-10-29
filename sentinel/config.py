"""Runtime settings (environment) and security policy (YAML)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = ROOT / "config" / "policy.yaml"


def _parse_operator_keys(raw: str) -> dict[str, str]:
    """'alice:key1,bob:key2' -> {'key1': 'alice', 'key2': 'bob'}"""
    out: dict[str, str] = {}
    for item in filter(None, (p.strip() for p in raw.split(","))):
        name, _, key = item.partition(":")
        if name and key:
            out[key.strip()] = name.strip()
    return out


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    operator_keys: dict[str, str] = field(default_factory=dict)
    policy_path: Path = DEFAULT_POLICY
    redis_url: str | None = None
    audit_db: Path = Path("data/audit.db")
    signing_key: str | None = None
    dev_mode: bool = False
    etherscan_api_key: str = ""
    trongrid_api_key: str = ""
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    bitcoin_api_url: str = "https://mempool.space/api"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    slack_webhook_url: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        e = os.getenv
        return cls(
            api_key=e("SENTINEL_API_KEY", ""),
            operator_keys=_parse_operator_keys(e("SENTINEL_OPERATOR_KEYS", "")),
            policy_path=Path(e("SENTINEL_POLICY", str(DEFAULT_POLICY))),
            redis_url=e("SENTINEL_REDIS_URL") or None,
            audit_db=Path(e("SENTINEL_AUDIT_DB", "data/audit.db")),
            signing_key=e("SENTINEL_SIGNING_KEY") or None,
            dev_mode=e("SENTINEL_DEV_MODE", "false").lower() in {"1", "true", "yes"},
            etherscan_api_key=e("ETHERSCAN_API_KEY", ""),
            trongrid_api_key=e("TRONGRID_API_KEY", ""),
            solana_rpc_url=e("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
            bitcoin_api_url=e("BITCOIN_API_URL", "https://mempool.space/api"),
            telegram_bot_token=e("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=e("TELEGRAM_CHAT_ID", ""),
            slack_webhook_url=e("SLACK_WEBHOOK_URL", ""),
            webhook_url=e("ALERT_WEBHOOK_URL", ""),
            webhook_secret=e("ALERT_WEBHOOK_SECRET", ""),
            log_level=e("SENTINEL_LOG_LEVEL", "INFO"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    policy_path = Path(path) if path else get_settings().policy_path
    with policy_path.open(encoding="utf-8") as fh:
        policy = yaml.safe_load(fh)
    policy["_base_dir"] = str(policy_path.resolve().parent)
    return policy


def load_list(policy: dict[str, Any], rel_path: str | None) -> set[str]:
    """Load a newline-separated address list (comments with #) relative to the policy file."""
    if not rel_path:
        return set()
    p = Path(rel_path)
    if not p.is_absolute():
        p = Path(policy.get("_base_dir", ".")) / p
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line.lower())
    return out
