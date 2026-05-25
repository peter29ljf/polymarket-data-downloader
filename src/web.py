"""Flask Web：API 配置、滑点、快速交易、持仓、交易记录"""

import logging
import os

from flask import Flask, render_template, jsonify, request
from src.config import get_env_path, get_config_path, Config, load_app_env
from src.key_generator import generate_credentials
from src.api_client import get_midpoint, get_token_ids, get_positions, get_balance_via_client
from src.trader import market_buy, market_sell
from src.storage import TradeStorage

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    )
    trade_storage = TradeStorage()

    @app.after_request
    def _cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp

    @app.route("/")
    def index():
        return render_template("index.html")

    # ---------- API 凭据 ----------
    @app.route("/api/generate-env", methods=["POST"])
    def api_generate_env():
        data = request.json or {}
        pk = (data.get("private_key") or data.get("PRIVATE_KEY") or "").strip()
        wallet = (data.get("wallet_address") or data.get("WALLET_ADDRESS") or "").strip()
        if not pk or not wallet:
            return jsonify({"success": False, "error": "需要 private_key 和 wallet_address"}), 400
        try:
            creds = generate_credentials(pk, wallet)
            return jsonify({"success": True, **creds})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            logger.exception("generate-env failed")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/env-status")
    def api_env_status():
        """返回是否已有 .env 及脱敏的 wallet（用于前端判断）"""
        load_app_env()
        wallet = os.environ.get("WALLET_ADDRESS", "")
        has_key = bool(os.environ.get("CLOB_API_KEY"))
        return jsonify({
            "has_env": has_key,
            "wallet_preview": f"{wallet[:10]}...{wallet[-6:]}" if len(wallet) >= 16 else wallet or "",
        })

    # ---------- 配置 ----------
    @app.route("/api/config", methods=["GET", "POST"])
    def api_config():
        cfg = Config.from_file()
        if request.method == "POST":
            data = request.json or {}
            cfg.slippage_pct = float(data.get("slippage_pct", cfg.slippage_pct))
            cfg.slippage_mode = str(data.get("slippage_mode", cfg.slippage_mode))
            cfg.to_file()
            return jsonify({"success": True, "slippage_pct": cfg.slippage_pct, "slippage_mode": cfg.slippage_mode})
        return jsonify({"slippage_pct": cfg.slippage_pct, "slippage_mode": cfg.slippage_mode})

    # ---------- 余额 ----------
    @app.route("/api/balance")
    def api_balance():
        load_app_env()
        result = get_balance_via_client()
        if result is None:
            return jsonify({"error": "无法获取余额（请先配置 .env）"}), 400
        return jsonify(result)

    # ---------- 持仓 ----------
    @app.route("/api/positions")
    def api_positions():
        load_app_env()
        wallet = os.environ.get("WALLET_ADDRESS", "")
        if not wallet:
            return jsonify({"error": "未配置 WALLET_ADDRESS", "positions": []}), 400
        positions = get_positions(wallet, "0")
        return jsonify({"wallet": wallet, "positions": positions})

    @app.route("/api/positions/close", methods=["POST"])
    def api_positions_close():
        data = request.json or {}
        token_id = (data.get("token_id") or data.get("tokenId") or "").strip()
        amount = data.get("amount")
        if not token_id:
            return jsonify({"success": False, "error": "缺少 token_id"}), 400
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "amount 必须为数字"}), 400
        if amount <= 0:
            return jsonify({"success": False, "error": "amount 必须大于 0"}), 400
        result = market_sell(token_id, amount, Config.from_file())
        if result.get("success"):
            trade_storage.append({
                "side": "sell",
                "token_id": token_id,
                "amount": amount,
                "status": "filled",
                "adjusted": result.get("adjusted", False),
                "avg_price": result.get("avg_price"),
                "order_id": result.get("order_id"),
            })
        return jsonify(result)

    # ---------- Token IDs / Midpoint ----------
    @app.route("/api/token-ids")
    def api_token_ids():
        slug = request.args.get("slug", "").strip()
        if not slug:
            return jsonify({"error": "缺少 slug", "items": []}), 400
        out = get_token_ids(slug)
        if out.get("error") and not (out.get("items")):
            return jsonify(out), 404
        return jsonify(out)

    @app.route("/api/midpoint")
    def api_midpoint():
        token_id = request.args.get("token_id", "").strip()
        if not token_id:
            return jsonify({"error": "缺少 token_id"}), 400
        mid = get_midpoint(token_id)
        if mid is None:
            return jsonify({"error": "无法获取中间价", "token_id": token_id}), 404
        return jsonify({"token_id": token_id, "mid": mid})

    # ---------- 快速交易 ----------
    @app.route("/api/trade/buy", methods=["POST"])
    def api_trade_buy():
        data = request.json or {}
        token_id = (data.get("token_id") or "").strip()
        amount = data.get("amount")
        if not token_id:
            return jsonify({"success": False, "error": "缺少 token_id"}), 400
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "amount 必须为数字"}), 400
        if amount <= 0:
            return jsonify({"success": False, "error": "amount 必须大于 0"}), 400
        result = market_buy(token_id, amount, Config.from_file())
        if result.get("success"):
            trade_storage.append({
                "side": "buy",
                "token_id": token_id,
                "amount_usdc": amount,
                "status": "partial_filled" if result.get("adjusted") else "filled",
                "avg_price": result.get("avg_price"),
                "slippage_pct": result.get("slippage_pct"),
                "order_id": result.get("order_id"),
            })
        else:
            trade_storage.append({
                "side": "buy",
                "token_id": token_id,
                "amount_usdc": amount,
                "status": "cancelled" if "取消" in (result.get("error") or "") else "failed",
                "error": result.get("error"),
            })
        return jsonify(result)

    @app.route("/api/trade/sell", methods=["POST"])
    def api_trade_sell():
        data = request.json or {}
        token_id = (data.get("token_id") or "").strip()
        amount = data.get("amount")
        if not token_id:
            return jsonify({"success": False, "error": "缺少 token_id"}), 400
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "amount 必须为数字"}), 400
        if amount <= 0:
            return jsonify({"success": False, "error": "amount 必须大于 0"}), 400
        result = market_sell(token_id, amount, Config.from_file())
        if result.get("success"):
            trade_storage.append({
                "side": "sell",
                "token_id": token_id,
                "amount_shares": result.get("sold_amount", amount),
                "status": "adjusted_filled" if result.get("adjusted") else "filled",
                "avg_price": result.get("avg_price"),
                "slippage_pct": result.get("slippage_pct"),
                "order_id": result.get("order_id"),
            })
        else:
            trade_storage.append({
                "side": "sell",
                "token_id": token_id,
                "amount_shares": amount,
                "status": "cancelled" if "取消" in (result.get("error") or "") else "failed",
                "error": result.get("error"),
            })
        return jsonify(result)

    # ---------- 交易记录 ----------
    @app.route("/api/trades")
    def api_trades():
        limit = request.args.get("limit", 200, type=int)
        return jsonify(trade_storage.load(limit=limit))

    # ---------- 清除所有数据 ----------
    @app.route("/api/clear-all", methods=["POST"])
    def api_clear_all():
        cleared = []
        errors = []

        # 1. 清除 data/.env（API 凭据）
        env_path = get_env_path()
        try:
            if env_path.exists():
                env_path.unlink()
            cleared.append("api_credentials")
            # 同步清除内存中的环境变量
            for key in ["CLOB_API_KEY", "CLOB_SECRET", "CLOB_PASS_PHRASE",
                        "PRIVATE_KEY", "WALLET_ADDRESS", "CLOB_HOST"]:
                os.environ.pop(key, None)
        except Exception as e:
            errors.append(f"清除凭据失败: {e}")

        # 2. 清除 data/trades.json（交易历史）
        try:
            trades_path = trade_storage.path
            if trades_path.exists():
                trades_path.unlink()
            cleared.append("trade_history")
        except Exception as e:
            errors.append(f"清除交易记录失败: {e}")

        if errors:
            return jsonify({"success": False, "cleared": cleared, "errors": errors}), 500
        return jsonify({"success": True, "cleared": cleared})

    return app
