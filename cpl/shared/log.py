"""Local prompt log (JSONL).

The gate appends one record per evaluated prompt. `stats` and `profile`
skills read these back. Everything is local; nothing leaves the machine.

Records are best-effort: a logging failure must never block a prompt.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List

# The gate appends a record on EVERY prompt, so the log would grow without
# bound. Keep it bounded: once it crosses the soft size cap, trim to the most
# recent _KEEP_RECORDS lines. stats/profile only ever need a recent window.
_MAX_BYTES = 2_000_000          # ~2 MB soft cap before a trim
_KEEP_RECORDS = 5_000           # lines retained on trim / default tail window


def append(log_path: Path, record: Dict[str, Any]) -> None:
    """Append a single JSONL record. Silent on failure (fail-open)."""
    try:
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        line = json.dumps(record, ensure_ascii=False)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        return
    # Cheap stat check; trim only fires when the file is actually large.
    try:
        if log_path.stat().st_size > _MAX_BYTES:
            _trim(log_path, _KEEP_RECORDS)
    except Exception:
        pass


def _trim(log_path: Path, keep: int) -> None:
    """Rewrite the log keeping only its last `keep` lines. Best-effort."""
    try:
        lines = _read_last_lines(log_path, keep)
        tmp = log_path.with_suffix(log_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for ln in lines:
                fh.write(ln + "\n")
        os.replace(tmp, log_path)
    except Exception:
        pass


def _read_last_lines(log_path: Path, n: int) -> List[str]:
    """Return the last n non-empty lines, reading from the end in chunks."""
    if n <= 0 or not log_path.is_file():
        return []
    try:
        with log_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            end = fh.tell()
            block = 65536
            data = b""
            newlines = 0
            pos = end
            # Read backwards until we've seen enough line breaks (or hit BOF).
            while pos > 0 and newlines <= n:
                step = min(block, pos)
                pos -= step
                fh.seek(pos)
                chunk = fh.read(step)
                data = chunk + data
                newlines += chunk.count(b"\n")
            text = data.decode("utf-8", errors="ignore")
    except Exception:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-n:]


def read_all(log_path: Path) -> List[Dict[str, Any]]:
    """Read every record. Skips malformed lines. Returns [] if missing."""
    return list(iter_records(log_path))


def tail(log_path: Path, n: int = _KEEP_RECORDS) -> List[Dict[str, Any]]:
    """Return up to the last n records, reading only the end of the file.

    Used by stats/profile so they don't parse the whole history each call.
    """
    out: List[Dict[str, Any]] = []
    for line in _read_last_lines(log_path, n):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


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
