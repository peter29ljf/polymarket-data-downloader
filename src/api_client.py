"""Polymarket 公共 API：midpoint、orderbook、token_ids、positions、balance"""

import logging
import os
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

MIDPOINT_URL = "https://clob.polymarket.com/midpoint"
BOOK_URL = "https://clob.polymarket.com/book"
GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
POSITIONS_URL = "https://data-api.polymarket.com/positions"
BALANCE_ALLOWANCE_URL = "https://clob.polymarket.com/balance-allowance"
TIMEOUT = 15


def get_midpoint(token_id: str) -> Optional[float]:
    """GET midpoint?token_id=xxx，返回中间价或 None"""
    if not token_id or not token_id.strip():
        return None
    try:
        r = requests.get(
            MIDPOINT_URL,
            params={"token_id": token_id.strip()},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, dict) and "mid" in data:
            return float(data["mid"])
        return None
    except Exception as e:
        logger.warning("get_midpoint failed: %s", e)
        return None


def get_book(token_id: str) -> Optional[dict]:
    """GET book?token_id=xxx，返回 { asks: [...], bids: [...] }"""
    if not token_id or not token_id.strip():
        return None
    try:
        r = requests.get(
            BOOK_URL,
            params={"token_id": token_id.strip()},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        logger.warning("get_book failed: %s", e)
        return None


def _parse_flexible_array(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = __import__("json").loads(s)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def get_token_ids(slug: str) -> dict:
    """
    从 gamma-api events?slug=xxx 获取所有市场的 token 列表（每个市场有 Yes/No 等 outcome）。
    返回 { "items": [{ "tokenid", "outcome", "groupItemTitle", "marketSlug", "eventSlug" }, ...], "error": "" }
    多市场时列出全部，供前端让用户选择交易目标。
    """
    slug = (slug or "").strip()
    if not slug:
        return {"items": [], "error": "slug 为空"}

    try:
        r = requests.get(
            GAMMA_EVENTS_URL,
            params={"slug": slug},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return {"items": [], "error": f"HTTP {r.status_code}"}
        raw = r.json()
        events = raw if isinstance(raw, list) else []
        open_events = [e for e in events if e and not e.get("closed")]
        if not open_events:
            return {"items": [], "error": "未找到开放赛事"}

        items = []
        seen = set()
        for event in open_events:
            for market in event.get("markets") or []:
                if market.get("closed"):
                    continue
                base_title = (market.get("groupItemTitle") or market.get("question") or market.get("slug") or "").strip()
                outcomes = _parse_flexible_array(market.get("outcomes"))
                token_ids = _parse_flexible_array(market.get("clobTokenIds"))
                for i, tid in enumerate(token_ids):
                    tid = str(tid or "").strip()
                    if not tid or tid in seen:
                        continue
                    seen.add(tid)
                    outcome = (outcomes[i] if i < len(outcomes) else f"Outcome{i}").strip()
                    display_title = f"{base_title} ({outcome})" if base_title else outcome
                    items.append({
                        "tokenid": tid,
                        "outcome": outcome,
                        "groupItemTitle": display_title,
                        "baseTitle": base_title or None,
                        "marketSlug": market.get("slug"),
                        "marketId": market.get("id"),
                        "eventSlug": event.get("slug") or slug,
                    })
        if not items:
            return {"items": [], "error": "未解析到 Token ID"}
        return {"items": items, "error": ""}
    except Exception as e:
        logger.warning("get_token_ids failed: %s", e)
        return {"items": [], "error": str(e)}


def get_positions(wallet: str, size_threshold: str = "0") -> list:
    """
    GET data-api positions?user=xxx&sizeThreshold=xxx
    官方返回 200 时 body 为 Position 数组，非对象包装。
    """
    wallet = (wallet or "").strip()
    if not wallet:
        return []
    try:
        r = requests.get(
            POSITIONS_URL,
            params={"user": wallet, "sizeThreshold": size_threshold},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "error" in data:
            logger.warning("get_positions API error: %s", data.get("error"))
            return []
        return []
    except Exception as e:
        logger.warning("get_positions failed: %s", e)
        return []


def get_balance_via_client() -> Optional[dict]:
    """
    使用当前 data/.env 中的凭据，通过 py_clob_client 查询 USDC.e 余额。
    返回 { "balance": float_usdc, "allowance": float_usdc } 或 None
    """
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, AssetType

        from src.config import load_app_env

        load_app_env()
        api_key = os.environ.get("CLOB_API_KEY")
        api_secret = os.environ.get("CLOB_SECRET")
        api_passphrase = os.environ.get("CLOB_PASS_PHRASE")
        private_key = (os.environ.get("PRIVATE_KEY") or "").replace("0x", "")
        wallet = os.environ.get("WALLET_ADDRESS")
        host = os.environ.get("CLOB_HOST", "https://clob.polymarket.com")
        if not all([api_key, api_secret, api_passphrase, private_key, wallet]):
            return None

        creds = ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        )
        client = ClobClient(host, key=private_key, chain_id=137, creds=creds, funder=wallet, signature_type=1)
        try:
            client.set_api_creds(client.create_or_derive_api_creds())
        except Exception:
            pass
        result = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        if not result:
            return None
        bal = int(result.get("balance") or 0)
        allow = int(result.get("allowance") or 0)
        return {"balance": bal / 1e6, "allowance": allow / 1e6}
    except Exception as e:
        logger.warning("get_balance_via_client failed: %s", e)
        return None
