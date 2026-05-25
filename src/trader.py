"""
市价买卖 + 滑点保护（partial/cancel）+ 卖出前持仓校验。
依赖 data/.env 与 config 中的滑点设置。
"""

import logging
import os
from typing import Optional

from src.config import get_env_path, get_config_path, Config, load_app_env
from src.api_client import get_midpoint, get_book, get_positions

logger = logging.getLogger(__name__)


def _load_env():
    load_app_env()


def _get_config() -> Config:
    return Config.from_file()


def _simulate_buy_from_asks(asks: list, amount_usdc: float) -> tuple:
    """
    模拟用 amount_usdc 按 asks 从低到高吃单，返回 (filled_shares, avg_price, total_cost).
    asks: [ {"price": "0.72", "size": "100"}, ... ]
    """
    filled = 0.0
    cost = 0.0
    remaining = amount_usdc
    for ask in asks:
        price = float(ask.get("price") or 0)
        size = float(ask.get("size") or 0)
        if price <= 0 or size <= 0 or remaining <= 0:
            continue
        can_spend = remaining
        can_buy = can_spend / price
        take = min(can_buy, size)
        if take <= 0:
            continue
        spend = take * price
        filled += take
        cost += spend
        remaining -= spend
        if remaining <= 0:
            break
    avg_price = cost / filled if filled else 0.0
    return filled, avg_price, cost


def _simulate_sell_to_bids(bids: list, amount_shares: float) -> tuple:
    """
    模拟卖出 amount_shares 到 bids（从高到低），返回 (filled_shares, avg_price, total_usdc).
    """
    filled = 0.0
    usdc = 0.0
    remaining = amount_shares
    for bid in bids:
        price = float(bid.get("price") or 0)
        size = float(bid.get("size") or 0)
        if price <= 0 or size <= 0 or remaining <= 0:
            continue
        take = min(remaining, size)
        filled += take
        usdc += take * price
        remaining -= take
        if remaining <= 0:
            break
    avg_price = usdc / filled if filled else 0.0
    return filled, avg_price, usdc


def _get_position_size(wallet: str, token_id: str) -> float:
    positions = get_positions(wallet, "0")
    for p in positions:
        if (p.get("asset") or p.get("token_id") or "").strip() == (token_id or "").strip():
            return float(p.get("size") or 0)
    return 0.0


def market_buy(
    token_id: str,
    amount_usdc: float,
    config: Optional[Config] = None,
) -> dict:
    """
    市价买入。先查 midpoint 与 orderbook，按滑点模式决定实际下单量，再提交 FOK 买单。
    返回 { "success": bool, "order_id"?, "error"?, "adjusted"?, "avg_price"?, "slippage_pct"?, "message" }
    """
    _load_env()
    cfg = config or _get_config()
    mid = get_midpoint(token_id)
    if mid is None or mid <= 0:
        return {"success": False, "error": "无法获取中间价"}

    book = get_book(token_id)
    if not book:
        return {"success": False, "error": "无法获取订单簿"}
    asks = list(book.get("asks") or [])
    asks.sort(key=lambda x: float(x.get("price") or 0))
    if not asks:
        return {"success": False, "error": "订单簿无 ask"}

    filled, avg_price, cost = _simulate_buy_from_asks(asks, amount_usdc)
    if filled <= 0:
        return {"success": False, "error": "订单簿深度不足，无法成交"}

    slip_ratio = cfg.slippage_ratio()
    max_price = mid * (1 + slip_ratio)
    actual_slip = (avg_price - mid) / mid if mid else 0

    if avg_price > max_price:
        if cfg.slippage_mode == "cancel":
            return {
                "success": False,
                "error": f"滑点超出 {cfg.slippage_pct}%（实际 {actual_slip*100:.2f}%），已取消整单",
                "avg_price": avg_price,
                "slippage_pct": actual_slip * 100,
            }
        # partial: 只吃到均价不超过 max_price 的量
        cum_filled, cum_cost = 0.0, 0.0
        for ask in asks:
            price = float(ask.get("price") or 0)
            size = float(ask.get("size") or 0)
            if price > max_price:
                break
            remaining_usdc = amount_usdc - cum_cost
            if remaining_usdc <= 0:
                break
            take = min(size, remaining_usdc / price)
            cum_filled += take
            cum_cost += take * price
        filled = cum_filled
        cost = cum_cost
        avg_price = cost / filled if filled else 0
        if filled <= 0:
            return {"success": False, "error": "滑点范围内无可用深度"}

    # 用 amount_usdc 下单时，FOK 市价买是按 USDC 金额；py_clob_client create_market_order 的 amount 是 USDC
    amount_to_order = cost  # USDC
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds, MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
    except ImportError:
        return {"success": False, "error": "未安装 py-clob-client"}

    host = os.environ.get("CLOB_HOST", "https://clob.polymarket.com")
    key = (os.environ.get("PRIVATE_KEY") or "").replace("0x", "")
    wallet = os.environ.get("WALLET_ADDRESS")
    if not all([key, wallet]):
        return {"success": False, "error": "未配置 PRIVATE_KEY 或 WALLET_ADDRESS"}

    creds = ApiCreds(
        api_key=os.environ.get("CLOB_API_KEY"),
        api_secret=os.environ.get("CLOB_SECRET"),
        api_passphrase=os.environ.get("CLOB_PASS_PHRASE"),
    )
    client = ClobClient(host, key=key, chain_id=137, creds=creds, funder=wallet, signature_type=1)
    try:
        client.set_api_creds(client.create_or_derive_api_creds())
    except Exception:
        pass

    try:
        order_args = MarketOrderArgs(token_id=token_id, amount=float(amount_to_order), side=BUY)
        signed = client.create_market_order(order_args)
        resp = client.post_order(signed, orderType=OrderType.FOK)
    except Exception as e:
        msg = str(e)
        if "invalid signature" in msg or "L2 authentication" in msg:
            try:
                client.set_api_creds(client.create_or_derive_api_creds())
                signed = client.create_market_order(order_args)
                resp = client.post_order(signed, orderType=OrderType.FOK)
            except Exception as e2:
                return {"success": False, "error": str(e2)}
        else:
            return {"success": False, "error": msg}

    if resp.get("success") is True:
        return {
            "success": True,
            "order_id": resp.get("orderID"),
            "avg_price": avg_price,
            "slippage_pct": (avg_price - mid) / mid * 100 if mid else 0,
            "amount_usdc": amount_to_order,
            "adjusted": amount_to_order < amount_usdc,
        }
    return {
        "success": False,
        "error": resp.get("errorMsg") or resp.get("error") or "下单失败",
        "avg_price": avg_price,
    }


def market_sell(
    token_id: str,
    amount_shares: float,
    config: Optional[Config] = None,
) -> dict:
    """
    市价卖出。先查持仓，不足则截断为持仓量；再按滑点逻辑决定是否 partial/cancel，提交 FOK 卖单。
    返回 { "success", "order_id"?, "error"?, "adjusted"?, "avg_price"?, "slippage_pct"?, "sold_amount" }
    """
    _load_env()
    cfg = config or _get_config()
    wallet = os.environ.get("WALLET_ADDRESS")
    if not wallet:
        return {"success": False, "error": "未配置 WALLET_ADDRESS"}

    position_size = _get_position_size(wallet, token_id)
    if position_size <= 0:
        return {"success": False, "error": "无对应持仓"}

    effective_amount = min(amount_shares, position_size)
    adjusted = effective_amount < amount_shares

    mid = get_midpoint(token_id)
    if mid is None or mid <= 0:
        return {"success": False, "error": "无法获取中间价"}

    book = get_book(token_id)
    if not book:
        return {"success": False, "error": "无法获取订单簿"}
    bids = list(book.get("bids") or [])
    bids.sort(key=lambda x: float(x.get("price") or 0), reverse=True)
    if not bids:
        return {"success": False, "error": "订单簿无 bid"}

    filled, avg_price, usdc = _simulate_sell_to_bids(bids, effective_amount)
    if filled <= 0:
        return {"success": False, "error": "订单簿深度不足"}

    slip_ratio = cfg.slippage_ratio()
    min_price = mid * (1 - slip_ratio)
    actual_slip = (mid - avg_price) / mid if mid else 0

    if avg_price < min_price:
        if cfg.slippage_mode == "cancel":
            return {
                "success": False,
                "error": f"滑点超出 {cfg.slippage_pct}%（卖价过低），已取消整单",
                "avg_price": avg_price,
                "slippage_pct": actual_slip * 100,
            }
        cum_filled, cum_usdc = 0.0, 0.0
        for bid in bids:
            price = float(bid.get("price") or 0)
            size = float(bid.get("size") or 0)
            if price < min_price:
                break
            remaining = effective_amount - cum_filled
            if remaining <= 0:
                break
            take = min(size, remaining)
            cum_filled += take
            cum_usdc += take * price
        filled = cum_filled
        avg_price = cum_usdc / filled if filled else 0
        if filled <= 0:
            return {"success": False, "error": "滑点范围内无可用深度"}
        effective_amount = filled

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds, MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import SELL
    except ImportError:
        return {"success": False, "error": "未安装 py-clob-client"}

    host = os.environ.get("CLOB_HOST", "https://clob.polymarket.com")
    key = (os.environ.get("PRIVATE_KEY") or "").replace("0x", "")
    creds = ApiCreds(
        api_key=os.environ.get("CLOB_API_KEY"),
        api_secret=os.environ.get("CLOB_SECRET"),
        api_passphrase=os.environ.get("CLOB_PASS_PHRASE"),
    )
    # 卖单尝试多种签名类型
    candidates = [(2, "POLY_GNOSIS_SAFE"), (1, "POLY_PROXY"), (0, "EOA")]
    last_error = None
    for sig_type, _ in candidates:
        try:
            client = ClobClient(host, key=key, chain_id=137, creds=creds, funder=wallet, signature_type=sig_type)
            try:
                client.set_api_creds(client.create_or_derive_api_creds())
            except Exception:
                pass
            order_args = MarketOrderArgs(token_id=token_id, amount=float(effective_amount), side=SELL)
            signed = client.create_market_order(order_args)
            resp = client.post_order(signed, orderType=OrderType.FOK)
            if resp.get("success") is True:
                return {
                    "success": True,
                    "order_id": resp.get("orderID"),
                    "avg_price": avg_price,
                    "slippage_pct": (mid - avg_price) / mid * 100 if mid else 0,
                    "sold_amount": effective_amount,
                    "adjusted": adjusted,
                }
            err = resp.get("errorMsg") or resp.get("error") or ""
            if "invalid signature" in str(err).lower():
                last_error = err
                continue
            return {"success": False, "error": err, "avg_price": avg_price}
        except Exception as e:
            msg = str(e)
            if "invalid signature" in msg.lower():
                last_error = msg
                continue
            return {"success": False, "error": msg}
    return {"success": False, "error": last_error or "所有签名类型均失败"}
