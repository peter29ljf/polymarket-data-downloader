"""
MCP 服务器：SSE 模式，端口 8001，暴露 6 个工具。
"""

import json
import logging
import os

from src.config import get_env_path, get_config_path, Config, load_app_env
from src.api_client import (
    get_midpoint as _api_get_midpoint,
    get_token_ids as fetch_token_ids,
    get_positions as _api_get_positions,
    get_balance_via_client,
)
from src.trader import market_buy as _trader_buy, market_sell as _trader_sell
from src.storage import TradeStorage

_trade_storage = TradeStorage()

logger = logging.getLogger(__name__)

# 供 main 使用的 FastMCP 实例
try:
    from fastmcp import FastMCP
except ImportError:
    FastMCP = None


def _ensure_env():
    load_app_env()


def _get_config() -> Config:
    return Config.from_file()


def _wallet() -> str:
    _ensure_env()
    return (os.environ.get("WALLET_ADDRESS") or "").strip()


def build_mcp():
    if FastMCP is None:
        raise RuntimeError("请安装 fastmcp: pip install fastmcp")
    mcp = FastMCP("Polymarket Trader")

    @mcp.tool
    def market_buy(token_id: str, amount: float) -> str:
        """市价买入。token_id 为 outcome token ID，amount 为 USDC 金额。应用当前滑点设置（部分成交或取消整单）。"""
        _ensure_env()
        result = _trader_buy(token_id, float(amount), _get_config())
        if result.get("success"):
            _trade_storage.append({
                "source": "mcp",
                "side": "buy",
                "token_id": token_id,
                "amount_usdc": float(amount),
                "status": "partial_filled" if result.get("adjusted") else "filled",
                "avg_price": result.get("avg_price"),
                "slippage_pct": result.get("slippage_pct"),
                "order_id": result.get("order_id"),
            })
        else:
            _trade_storage.append({
                "source": "mcp",
                "side": "buy",
                "token_id": token_id,
                "amount_usdc": float(amount),
                "status": "cancelled" if "取消" in (result.get("error") or "") else "failed",
                "error": result.get("error"),
            })
        return json.dumps(result, ensure_ascii=False)

    @mcp.tool
    def market_sell(token_id: str, amount: float) -> str:
        """市价卖出。amount 为 shares 数量。会先检查持仓，不足则只卖持有部分；并应用滑点设置。"""
        _ensure_env()
        result = _trader_sell(token_id, float(amount), _get_config())
        if result.get("success"):
            _trade_storage.append({
                "source": "mcp",
                "side": "sell",
                "token_id": token_id,
                "amount_shares": result.get("sold_amount", float(amount)),
                "status": "adjusted_filled" if result.get("adjusted") else "filled",
                "avg_price": result.get("avg_price"),
                "slippage_pct": result.get("slippage_pct"),
                "order_id": result.get("order_id"),
            })
        else:
            _trade_storage.append({
                "source": "mcp",
                "side": "sell",
                "token_id": token_id,
                "amount_shares": float(amount),
                "status": "cancelled" if "取消" in (result.get("error") or "") else "failed",
                "error": result.get("error"),
            })
        return json.dumps(result, ensure_ascii=False)

    @mcp.tool
    def get_midpoint(token_id: str) -> str:
        """查询指定 token 的当前中间价。GET https://clob.polymarket.com/midpoint?token_id=xxx"""
        mid = _api_get_midpoint(token_id)
        if mid is None:
            return json.dumps({"error": "无法获取中间价", "token_id": token_id})
        return json.dumps({"token_id": token_id, "mid": mid})

    @mcp.tool
    def get_token_ids(slug: str) -> str:
        """从市场 slug 获取该事件下所有市场的交易 token 列表。返回 items 数组，每项含 tokenid、outcome、groupItemTitle 等，供选择后交易。"""
        out = fetch_token_ids(slug)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool
    def get_positions() -> str:
        """查询当前钱包的全部持仓列表（过滤 currentValue <= 2 的灰尘持仓需在前端或调用方处理）。"""
        wallet = _wallet()
        if not wallet:
            return json.dumps({"error": "未配置 WALLET_ADDRESS", "positions": []})
        positions = _api_get_positions(wallet, "0")
        return json.dumps({"wallet": wallet, "positions": positions}, ensure_ascii=False)

    @mcp.tool
    def get_balance() -> str:
        """查询钱包可用 USDC.e 余额和授权额度。balance/allowance 单位为 USDC（已除以 1e6）。"""
        _ensure_env()
        result = get_balance_via_client()
        if result is None:
            return json.dumps({"error": "无法获取余额（请检查 .env 与 API 凭据）"})
        return json.dumps(result, ensure_ascii=False)

    return mcp


def run_mcp_server(port: int = 8001):
    mcp = build_mcp()
    mcp.run(transport="sse", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_mcp_server()
