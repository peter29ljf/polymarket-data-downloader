"""从私钥生成 CLOB API 凭据并写入 data/.env"""

import os
from pathlib import Path

from src.config import get_data_dir, get_env_path


def _normalize_key(key: str) -> str:
    k = (key or "").strip()
    if k.startswith("0x"):
        k = k[2:]
    return k


def _extract_creds(creds) -> tuple:
    """从 py_clob_client 返回的 creds 中提取 api_key, api_secret, api_passphrase"""
    if hasattr(creds, "api_key") and hasattr(creds, "api_secret") and hasattr(creds, "api_passphrase"):
        return (creds.api_key or "", creds.api_secret or "", creds.api_passphrase or "")
    if isinstance(creds, dict):
        return (
            creds.get("api_key") or creds.get("api_key_hex") or "",
            creds.get("api_secret") or creds.get("api_secret_hex") or "",
            creds.get("api_passphrase") or creds.get("passphrase") or "",
        )
    api_key = getattr(creds, "api_key", None) or getattr(creds, "api_key_hex", "")
    api_secret = getattr(creds, "api_secret", None) or getattr(creds, "api_secret_hex", "")
    api_passphrase = getattr(creds, "api_passphrase", None) or getattr(creds, "passphrase", "")
    return (api_key or "", api_secret or "", api_passphrase or "")


def generate_credentials(private_key: str, wallet_address: str) -> dict:
    """
    使用 py_clob_client 从私钥派生 CLOB_API_KEY / CLOB_SECRET / CLOB_PASS_PHRASE。
    写入 data/.env，并返回三个凭据。
    """
    pk = _normalize_key(private_key)
    wallet = (wallet_address or "").strip()
    if len(pk) != 64:
        raise ValueError("私钥应为 64 位十六进制（可带 0x 前缀）")
    if not wallet.startswith("0x") or len(wallet) != 42:
        raise ValueError("钱包地址格式不正确（0x + 40 位）")

    try:
        from py_clob_client.client import ClobClient
    except ImportError as e:
        raise RuntimeError("请安装 py-clob-client: pip install py-clob-client") from e

    host = "https://clob.polymarket.com"
    chain_id = 137
    client = ClobClient(host, key=pk, chain_id=chain_id)
    try:
        creds = client.create_api_key()
    except Exception:
        creds = client.derive_api_key()

    api_key, api_secret, api_passphrase = _extract_creds(creds)
    if not api_key or not api_secret:
        raise RuntimeError("API 凭据生成结果不完整，请重试或检查 py-clob-client 版本")

    env_content = f"""# Polymarket Trader - 自动生成
CLOB_API_KEY={api_key}
CLOB_SECRET={api_secret}
CLOB_PASS_PHRASE={api_passphrase}
PRIVATE_KEY={pk}
WALLET_ADDRESS={wallet}
CLOB_HOST={host}
"""

    env_path = get_env_path()
    get_data_dir().mkdir(parents=True, exist_ok=True)
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    return {
        "CLOB_API_KEY": api_key,
        "CLOB_SECRET": api_secret,
        "CLOB_PASS_PHRASE": api_passphrase,
    }
