"""Local prompt log (JSONL).

The gate appends one record per evaluated prompt. `stats` and `profile`
skills read these back. Everything is local; nothing leaves the machine.

Records are best-effort: a logging failure must never block a prompt.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List


def append(log_path: Path, record: Dict[str, Any]) -> None:
    """Append a single JSONL record. Silent on failure (fail-open)."""
    try:
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        line = json.dumps(record, ensure_ascii=False)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def read_all(log_path: Path) -> List[Dict[str, Any]]:
    """Read every record. Skips malformed lines. Returns [] if missing."""
    return list(iter_records(log_path))


def iter_records(log_path: Path) -> Iterator[Dict[str, Any]]:
    if not log_path.is_file():
        return
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except Exception:
        return
