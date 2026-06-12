"""Prompt-framework library for the expand skill.

Frameworks are declarative JSON files: a name, aliases, a one-line description,
and an ordered list of sections (label + guidance). Loaded from the plugin's
frameworks/ dir and from ~/.cpl/frameworks/ (user files win on a name/alias
collision). Fully fail-safe — a missing dir or bad file is skipped.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Framework:
    name: str
    description: str
    sections: List[Dict[str, str]]            # [{"label":..., "guidance":...}]
    aliases: List[str] = field(default_factory=list)


# Hard-coded fallback so expand never breaks even if no files load.
_DEFAULT = Framework(
    name="default",
    description="Task / Anchor / Constraints / Done-when — the default structure.",
    sections=[
        {"label": "Task", "guidance": "the core ask in one line"},
        {"label": "Anchor", "guidance": "file/function/error to act on"},
        {"label": "Constraints", "guidance": "what to preserve / avoid"},
        {"label": "Done when", "guidance": "how success is verified"},
    ],
)


def _plugin_dir() -> Path:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        return Path(root) / "frameworks"
    return Path(__file__).resolve().parents[2] / "frameworks"


def _user_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".cpl" / "frameworks"


def _parse(path: Path) -> Optional[Framework]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", "")).strip()
    sections_in = data.get("sections")
    if not name or not isinstance(sections_in, list) or not sections_in:
        return None
    sections = []
    for s in sections_in:
        if isinstance(s, dict) and s.get("label"):
            sections.append({"label": str(s["label"]),
                             "guidance": str(s.get("guidance", ""))})
    if not sections:
        return None
    aliases = [str(a).lower() for a in data.get("aliases", []) if str(a).strip()]
    return Framework(name=name, description=str(data.get("description", "")),
                     sections=sections, aliases=aliases)


def load_frameworks() -> Dict[str, Framework]:
    """Map every name + alias (lowercased) to its Framework. User dir overrides."""
    out: Dict[str, Framework] = {}
    for d in (_plugin_dir(), _user_dir()):
        try:
            if not d.is_dir():
                continue
            files = sorted(d.glob("*.json"))
        except Exception:
            continue
        for fp in files:
            fw = _parse(fp)
            if fw is None:
                continue
            for key in [fw.name.lower(), *fw.aliases]:
                out[key] = fw
    out.setdefault("default", _DEFAULT)
    return out


def resolve(token: str, cfg: Dict) -> Tuple[Framework, bool]:
    """Resolve the first CLI token to a framework.

    Returns (framework, token_consumed). A token matching a known name/alias is
    consumed; otherwise the configured default_framework (fallback 'default') is
    returned and the token is left for the prompt.
    """
    frameworks = load_frameworks()
    key = (token or "").strip().lower()
    if key and key in frameworks:
        return frameworks[key], True
    exp = cfg.get("expand", {}) if isinstance(cfg, dict) else {}
    default_name = str(exp.get("default_framework", "default")).lower()
    fw = frameworks.get(default_name) or frameworks.get("default") or _DEFAULT
    return fw, False


def list_frameworks() -> List[Tuple[str, str]]:
    """Unique (name, description) pairs, sorted by name."""
    seen: Dict[str, str] = {}
    for fw in load_frameworks().values():
        seen[fw.name] = fw.description
    return sorted(seen.items())
