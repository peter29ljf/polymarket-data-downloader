"""
同时启动 Flask Web (8000) 与 MCP SSE 服务器 (8001)。
"""

import logging
import sys
import threading

from src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def run_mcp():
    try:
        from src.mcp_server import run_mcp_server
        cfg = Config.from_file()
        run_mcp_server(port=cfg.mcp_port)
    except Exception as e:
        logger.exception("MCP server failed: %s", e)


def main():
    cfg = Config.from_file()
    cfg.to_file()

    # 在后台线程启动 MCP（FastMCP run() 会阻塞）
    mcp_thread = threading.Thread(target=run_mcp, daemon=True)
    mcp_thread.start()
    logger.info("MCP SSE server starting on port %s (daemon)", cfg.mcp_port)

    # 主线程运行 Flask
    from src.web import create_app
    app = create_app()
    logger.info("Flask Web: http://%s:%s", cfg.web_host, cfg.web_port)
    app.run(host=cfg.web_host, port=cfg.web_port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
