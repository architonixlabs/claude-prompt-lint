"""scope skill — /cpl scope <prompt>

Extracts file paths and symbol-ish names referenced in a prompt and checks them
against the repo, so a typo or stale reference ("fix auth.py" when the file is
`authn.py`) gets caught before you send. Pure filesystem — no model, no network.

Heuristics, not a parser: it looks for things that *look* like file paths and
identifiers, then verifies the files exist and the symbols appear somewhere in
tracked source. Best-effort: it reports what it could and couldn't find.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from cpl.registry import Context, Result, Skill

# file.ext or a/b/c.ext — must have an extension to avoid matching prose.
_FILE_RE = re.compile(r"\b[\w./\\-]+\.[A-Za-z][A-Za-z0-9]{0,5}\b")
# func(), Obj.method, snake_case, CamelCase — candidate symbols.
_SYMBOL_RE = re.compile(
    r"\b\w+\(\)|\b[A-Za-z_]\w*\.[A-Za-z_]\w+\b|\b[a-z]+_[a-z_]+\b|\b[A-Z][a-z0-9]+[A-Z]\w*\b"
)

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
              "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode"}
_MAX_FILES_SCAN = 4000  # symbol search cap, so a huge repo can't hang the skill


def _repo_root(ctx: Context) -> Path:
    return Path(ctx.cwd or os.getcwd())


def _find_file(root: Path, ref: str) -> str:
    """Return a match note for a referenced file: exact, basename, or missing."""
    ref_norm = ref.replace("\\", "/")
    candidate = (root / ref_norm)
    if candidate.is_file():
        return f"✓ {ref} — found"
    # Try matching by basename anywhere in the tree.
    base = os.path.basename(ref_norm)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if base in filenames:
            rel = os.path.relpath(os.path.join(dirpath, base), root)
            return f"~ {ref} — not at that path, but `{rel}` exists"
    return f"✗ {ref} — no such file in repo"


def _iter_source_files(root: Path):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if count >= _MAX_FILES_SCAN:
                return
            # Only scan plausibly-text source files.
            if fn.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                            ".java", ".rb", ".c", ".h", ".cpp", ".cs", ".php",
                            ".sh", ".sql", ".md", ".json", ".yaml", ".yml",
                            ".css", ".html", ".vue", ".svelte")):
                count += 1
                yield Path(dirpath) / fn


def _symbol_present(root: Path, symbol: str) -> bool:
    needle = symbol.replace("()", "")
    if not needle:
        return False
    for f in _iter_source_files(root):
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if needle in line:
                        return True
        except Exception:
            continue
    return False


def run(ctx: Context) -> Result:
    target = (ctx.args or ctx.prompt or "").strip()
    if not target:
        return Result(
            action="message",
            payload="[cpl scope] Usage: /cpl scope <prompt that references files/symbols>",
        )

    root = _repo_root(ctx)
    if not root.is_dir():
        return Result(
            action="message",
            payload=f"[cpl scope] Working dir not found: {root}",
        )

    files = []
    seen_files = set()
    for m in _FILE_RE.findall(target):
        if m not in seen_files and "." in os.path.basename(m):
            seen_files.add(m)
            files.append(m)

    symbols = []
    seen_syms = set()
    for m in _SYMBOL_RE.findall(target):
        # Skip things already counted as files.
        if m in seen_syms or any(m in f for f in files):
            continue
        seen_syms.add(m)
        symbols.append(m)

    if not files and not symbols:
        return Result(
            action="message",
            payload="🔎 cpl scope — no file paths or symbols detected in the prompt.",
        )

    lines = ["🔎 cpl scope", "", f"  Repo: {root}", ""]

    if files:
        lines.append("  Files referenced:")
        for ref in files[:15]:
            lines.append(f"    {_find_file(root, ref)}")
        lines.append("")

    # Symbol scan is the expensive part — cap how many we check.
    if symbols:
        lines.append("  Symbols referenced (searched in tracked source):")
        for sym in symbols[:8]:
            present = _symbol_present(root, sym)
            mark = "✓" if present else "✗"
            note = "found" if present else "not found in repo"
            lines.append(f"    {mark} {sym} — {note}")
        if len(symbols) > 8:
            lines.append(f"    … and {len(symbols) - 8} more not checked (cap)")

    missing = [f for f in files if _find_file(root, f).startswith("✗")]
    if missing:
        lines += [
            "",
            "  ⚠️  Some referenced files don't exist — check for typos or stale "
            "paths before sending.",
        ]

    return Result(action="message", payload="\n".join(lines))


SKILL = Skill(name="scope", run=run, command="scope")
