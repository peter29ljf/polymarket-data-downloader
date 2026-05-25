"""配置管理：滑点、模式、路径"""

import json
from dataclasses import dataclass
from pathlib import Path


def get_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def get_env_path() -> Path:
    return get_data_dir() / ".env"


def load_app_env():
    """加载 poly-trader/data/.env 到环境变量，override=True 确保不被系统/其它项目覆盖"""
    try:
        from dotenv import load_dotenv
        load_dotenv(get_env_path(), override=True)
    except Exception:
        pass


def get_config_path() -> Path:
    return get_data_dir() / "config.json"


def get_trades_path() -> Path:
    return get_data_dir() / "trades.json"


@dataclass
class Config:
    slippage_pct: float = 5.0
    slippage_mode: str = "partial"  # "partial" | "cancel"
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    mcp_port: int = 8001
    clob_host: str = "https://clob.polymarket.com"
    chain_id: int = 137

    @classmethod
    def from_file(cls) -> "Config":
        path = get_config_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(
                    slippage_pct=float(data.get("slippage_pct", 5.0)),
                    slippage_mode=str(data.get("slippage_mode", "partial")),
                    web_host=str(data.get("web_host", "0.0.0.0")),
                    web_port=int(data.get("web_port", 8000)),
                    mcp_port=int(data.get("mcp_port", 8001)),
                    clob_host=str(data.get("clob_host", "https://clob.polymarket.com")),
                    chain_id=int(data.get("chain_id", 137)),
                )
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def to_file(self):
        path = get_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "slippage_pct": self.slippage_pct,
                    "slippage_mode": self.slippage_mode,
                    "web_host": self.web_host,
                    "web_port": self.web_port,
                    "mcp_port": self.mcp_port,
                    "clob_host": self.clob_host,
                    "chain_id": self.chain_id,
                },
                f,
                indent=2,
            )

    def slippage_ratio(self) -> float:
        return self.slippage_pct / 100.0
