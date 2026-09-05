"""Debug NDJSON logger for session 6e8711."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_LOG_PATH = Path("/var/www/html/ai_agents/glancy/.cursor/debug-6e8711.log")


def dbg(hypothesis_id: str, location: str, message: str, data: dict[str, Any] | None = None) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "6e8711",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
