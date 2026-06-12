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
# Candidate symbols, deliberately restricted to *shapes that read as code* so we
# don't drag in prose. A bare snake_case word is too ambiguous with English
# ("sign_in", "make_it"), so it's only counted when written as a call.
#   foo()  obj.method  module.attr  CamelCase  snake_case()
_SYMBOL_RE = re.compile(
    r"\b\w+\(\)"                       # a call: foo()  /  parse_config()
    r"|\b[A-Za-z_]\w*\.[A-Za-z_]\w+\b"  # dotted: obj.method, mod.attr
    r"|\b[A-Z][a-z0-9]+[A-Z]\w*\b"      # CamelCase: OrderRepository
)

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
              "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode"}
_MAX_FILES_SCAN = 4000  # symbol search cap, so a huge repo can't hang the skill


def _repo_root(ctx: Context) -> Path:
    return Path(ctx.cwd or os.getcwd())


def _build_basename_index(root: Path):
    """Walk the repo ONCE, mapping basename -> first relative path seen.

    Capped at _MAX_FILES_SCAN so a huge monorepo can't make /cpl scope hang.
    Returns (index, capped) where `capped` signals the walk was truncated.
    """
    index = {}
    count = 0
    capped = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if count >= _MAX_FILES_SCAN:
                capped = True
                return index, capped
            count += 1
            if fn not in index:
                index[fn] = os.path.relpath(os.path.join(dirpath, fn), root)
    return index, capped


def _find_file(root: Path, ref: str, index, capped: bool) -> str:
    """Classify a referenced file against the pre-built basename index."""
    ref_norm = ref.replace("\\", "/")
    if (root / ref_norm).is_file():
        return f"✓ {ref} — found"
    base = os.path.basename(ref_norm)
    if base in index:
        return f"~ {ref} — not at that path, but `{index[base]}` exists"
    if capped:
        return f"? {ref} — not found in the first {_MAX_FILES_SCAN} files (repo too large to fully scan)"
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


def _symbols_present(root: Path, symbols):
    """Check many symbols in ONE pass over the source tree.

    Returns a set of the symbols found. Reading each file once and testing all
    needles avoids re-walking the repo per symbol (which was up to 8x the work).
    Short-circuits as soon as every symbol is located.
    """
    # Compile a word-boundary regex per needle so `parseToken` does NOT match
    # `parseTokenStream` (a raw substring search produced false "found" hits).
    needles = {}
    for s in symbols:
        base = s.replace("()", "")
        if base:
            needles[s] = re.compile(r"\b" + re.escape(base) + r"\b")
    found = set()
    if not needles:
        return found
    for f in _iter_source_files(root):
        if len(found) == len(needles):
            break
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue
        for sym, pat in needles.items():
            if sym not in found and pat.search(content):
                found.add(sym)
    return found


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

    # Walk the tree once; reuse the index for every file lookup below.
    file_results = {}
    if files:
        index, capped = _build_basename_index(root)
        for ref in files[:15]:
            file_results[ref] = _find_file(root, ref, index, capped)
        lines.append("  Files referenced:")
        for ref in files[:15]:
            lines.append(f"    {file_results[ref]}")
        lines.append("")

    # Symbol scan is the expensive part — cap how many we check, and resolve
    # them all in a single pass over the source tree.
    if symbols:
        checked = symbols[:8]
        found = _symbols_present(root, checked)
        lines.append("  Symbols referenced (searched in tracked source):")
        for sym in checked:
            mark = "✓" if sym in found else "✗"
            note = "found" if sym in found else "not found in repo"
            lines.append(f"    {mark} {sym} — {note}")
        if len(symbols) > 8:
            lines.append(f"    … and {len(symbols) - 8} more not checked (cap)")

    missing = [ref for ref, note in file_results.items() if note.startswith("✗")]
    if missing:
        lines += [
            "",
            "  ⚠️  Some referenced files don't exist — check for typos or stale "
            "paths before sending.",
        ]

    return Result(action="message", payload="\n".join(lines))


SKILL = Skill(name="scope", run=run, command="scope")
