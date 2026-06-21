"""Deterministic project scanner for the `init` skill.

Gathers facts about a repo — name, languages, build/test commands, layout, git —
using only the standard library and only by reading files (no subprocess). Fully
fail-safe: any sub-detector error is swallowed and that fact is omitted, so
`scan` always returns a dict and never raises.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
              "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
              ".github"}
_MAX_FILES = 4000

_LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".rb": "Ruby", ".c": "C", ".h": "C", ".cpp": "C++",
    ".cs": "C#", ".php": "PHP", ".sh": "Shell", ".sql": "SQL",
    ".md": "Markdown", ".css": "CSS", ".html": "HTML", ".vue": "Vue",
    ".svelte": "Svelte", ".kt": "Kotlin", ".swift": "Swift",
}


def _languages(root: Path) -> List[str]:
    counts: Counter = Counter()
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if seen >= _MAX_FILES:
                break
            seen += 1
            lang = _LANG_BY_EXT.get(Path(fn).suffix.lower())
            if lang:
                counts[lang] += 1
        if seen >= _MAX_FILES:
            break
    return [lang for lang, _ in counts.most_common(5)]


def _commands(root: Path, manifests: List[str]) -> Dict[str, str]:
    cmds: Dict[str, str] = {}
    if "package.json" in manifests:
        cmds["install"] = "npm install"
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
        except Exception:
            scripts = {}
        if "test" in scripts:
            cmds["test"] = "npm test"
        if "build" in scripts:
            cmds["build"] = "npm run build"
        if "start" in scripts:
            cmds["run"] = "npm start"
    if {"pyproject.toml", "requirements.txt", "setup.py"} & set(manifests):
        if "requirements.txt" in manifests:
            cmds.setdefault("install", "pip install -r requirements.txt")
        else:
            cmds.setdefault("install", "pip install -e .")
        if (root / "tests").is_dir():
            cmds.setdefault("test", "python -m unittest discover -s tests")
    if "Cargo.toml" in manifests:
        cmds.setdefault("install", "cargo build")
        cmds.setdefault("test", "cargo test")
        cmds.setdefault("run", "cargo run")
    if "go.mod" in manifests:
        cmds.setdefault("test", "go test ./...")
        cmds.setdefault("build", "go build ./...")
    return cmds


def _manifests(root: Path) -> List[str]:
    names = ["package.json", "pyproject.toml", "requirements.txt", "setup.py",
             "Cargo.toml", "go.mod", "Makefile", "pom.xml", "build.gradle"]
    return [n for n in names if (root / n).is_file()]


def _layout(root: Path) -> List[str]:
    out = []
    try:
        for p in sorted(root.iterdir()):
            if p.is_dir() and p.name not in _SKIP_DIRS and not p.name.startswith("."):
                out.append(p.name + "/")
    except Exception:
        return out
    return out[:10]


def _git(root: Path) -> Dict[str, str]:
    git: Dict[str, str] = {}
    head = root / ".git" / "HEAD"
    cfg = root / ".git" / "config"
    try:
        if head.is_file():
            m = re.match(r"ref:\s*refs/heads/(.+)", head.read_text(encoding="utf-8").strip())
            if m:
                git["branch"] = m.group(1).strip()
    except Exception:
        pass
    try:
        if cfg.is_file():
            m = re.search(r"\[remote \"origin\"\][^\[]*?url\s*=\s*(\S+)",
                          cfg.read_text(encoding="utf-8"))
            if m:
                url = m.group(1)
                url = re.sub(r"^https?://[^@/]*@", "https://", url)
                url = re.sub(r"^https?://", "", url)
                url = re.sub(r"^git@([^:]+):", r"\1/", url)
                url = re.sub(r"\.git$", "", url)
                git["remote"] = url
    except Exception:
        pass
    return git


def _entry_points(root: Path) -> List[str]:
    candidates = ["main.py", "app.py", "manage.py", "src/main.py", "index.js",
                  "src/index.js", "src/main.ts", "hooks/dispatcher.py", "cmd"]
    return [c for c in candidates if (root / c).exists()]


def scan(root) -> Dict[str, Any]:
    """Return a facts dict about the repo. Never raises."""
    try:
        root = Path(root)
        name = root.name or "project"
        facts: Dict[str, Any] = {"name": name}
        try:
            facts["manifests"] = _manifests(root)
        except Exception:
            facts["manifests"] = []
        for key, fn in (("languages", lambda: _languages(root)),
                        ("layout", lambda: _layout(root)),
                        ("git", lambda: _git(root)),
                        ("entry_points", lambda: _entry_points(root))):
            try:
                facts[key] = fn()
            except Exception:
                facts[key] = [] if key != "git" else {}
        try:
            facts["commands"] = _commands(root, facts.get("manifests", []))
        except Exception:
            facts["commands"] = {}
        # Prefer git-remote basename for the name when available.
        remote = facts.get("git", {}).get("remote", "")
        if remote:
            facts["name"] = remote.rstrip("/").split("/")[-1] or name
        return facts
    except Exception:
        return {"name": "project", "languages": [], "manifests": [],
                "commands": {}, "layout": [], "git": {}, "entry_points": []}
