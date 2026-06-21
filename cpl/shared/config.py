"""Config loader for claude-prompt-lint.

Resolution order (later overrides earlier):
  1. Built-in DEFAULTS below.
  2. config/cpl.config.json shipped with the plugin.
  3. ~/.cpl/config.json  (user-level override, optional).
  4. $CPL_CONFIG  (explicit path override, optional).

Fail-safe: any read/parse error falls back to whatever loaded so far,
never raises. A broken config must never break the user's workflow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "mode": "warn",                 # "warn" | "block"
    "feedback_style": "coach",      # "coach" (brief the assistant) | "note" (classic user note)
    "bypass_prefix": "!!",
    "min_length_skip": 40,
    "block_threshold": 50,
    "use_model": False,
    "model": "qwen2.5:3b-instruct",
    "model_endpoint": "http://localhost:11434/api/generate",
    "model_timeout_ms": 1500,
    "fail_open": True,
    "log_path": "~/.cpl/prompts.log.jsonl",
    "debug_log": False,
    "skills": {
        "gate": True,
        "rewrite": True,
        "stats": True,
        "explain": True,
        "profile": False,
        "expand": False,
        "scope": False,
        "template": False,
    },
}


def _plugin_root() -> Path:
    """Plugin install dir. Prefers $CLAUDE_PLUGIN_ROOT, falls back to repo root."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env)
    # cpl/shared/config.py -> repo root is two parents up from cpl/.
    return Path(__file__).resolve().parents[2]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override into a copy of base, one level deep for nested dicts."""
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            merged = dict(out[key])
            merged.update(val)
            out[key] = merged
        else:
            out[key] = val
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULTS)

    shipped = _plugin_root() / "config" / "cpl.config.json"
    if shipped.is_file():
        cfg = _deep_merge(cfg, _load_json(shipped))

    user = Path.home() / ".cpl" / "config.json"
    if user.is_file():
        cfg = _deep_merge(cfg, _load_json(user))

    explicit = os.environ.get("CPL_CONFIG")
    if explicit:
        p = Path(os.path.expanduser(explicit))
        if p.is_file():
            cfg = _deep_merge(cfg, _load_json(p))

    return cfg


def resolve_log_path(cfg: Dict[str, Any]) -> Path:
    """Expand ~ and env vars in log_path; ensure parent dir exists best-effort."""
    raw = cfg.get("log_path") or DEFAULTS["log_path"]
    path = Path(os.path.expanduser(os.path.expandvars(str(raw))))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return path
