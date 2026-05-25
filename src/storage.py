"""交易记录存储 trades.json"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from src.config import get_trades_path


class TradeStorage:
    def __init__(self):
        self.path = get_trades_path()
        self._lock = threading.Lock()

    def _read(self) -> List[dict]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _write(self, data: List[dict]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def append(self, record: dict):
        with self._lock:
            data = self._read()
            record["created_at"] = datetime.utcnow().isoformat() + "Z"
            data.append(record)
            self._write(data)

    def load(self, limit: int = 200) -> List[dict]:
        with self._lock:
            data = self._read()
        data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return data[:limit]
