"""init skill — /cpl init [--quick]

Writes a concise, cpl-managed project-context section into the project-root
CLAUDE.md (which Claude Code loads natively every session — zero per-turn token
cost). cpl fills a deterministic factual baseline; unless --quick, the command
layer (Claude) then enriches the section in place.

Merge-safe: only the text between the cpl markers is touched. Idempotent.
Fail-safe: reports a clear message on a write error; never raises.
"""

from __future__ import annotations

import os
from pathlib import Path

from cpl.registry import Context, Result, Skill
from cpl.shared import project

_START = "<!-- cpl:context:start -->"
_END = "<!-- cpl:context:end -->"


def _merge_section(existing: str, section: str) -> str:
    """Replace the delimited cpl section in `existing`, else append it.

    Tolerates duplicate markers by replacing from the first start to the last
    end. Pure and total."""
    if not existing.strip():
        return section
    i = existing.find(_START)
    if i == -1:
        return existing.rstrip() + "\n\n" + section + "\n"
    j = existing.rfind(_END)
    if j == -1 or j < i:
        return existing.rstrip() + "\n\n" + section + "\n"
    return existing[:i] + section + existing[j + len(_END):]


def _render(facts) -> str:
    lines = [_START,
             "## Project context (maintained by `cpl` — run `/cpl init` to refresh)",
             ""]
    lines.append(f"**Project:** {facts.get('name', 'project')}")
    langs = facts.get("languages") or []
    if langs:
        lines.append(f"**Stack:** {', '.join(langs)}")
    cmds = facts.get("commands") or {}
    if cmds:
        parts = [f"{k} `{v}`" for k, v in cmds.items()]
        lines.append("**Commands:** " + " · ".join(parts))
    layout = facts.get("layout") or []
    if layout:
        lines.append(f"**Layout:** {' · '.join(layout)}")
    git = facts.get("git") or {}
    if git.get("remote"):
        branch = f" (branch `{git['branch']}`)" if git.get("branch") else ""
        lines.append(f"**Git:** {git['remote']}{branch}")
    eps = facts.get("entry_points") or []
    if eps:
        lines.append(f"**Entry points:** {', '.join(eps)}")
    lines += ["",
              "<!-- cpl:enrich — architecture, conventions, gotchas go here -->",
              _END]
    return "\n".join(lines)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".cpltmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run(ctx: Context) -> Result:
    if ctx.event != "command":
        return Result(action="pass")

    args = (ctx.args or "").strip()
    quick = False
    if args.split()[:1] == ["--quick"]:
        quick = True

    cfg = ctx.config or {}
    init_cfg = cfg.get("init", {}) if isinstance(cfg.get("init"), dict) else {}
    fname = init_cfg.get("claude_md", "CLAUDE.md") or "CLAUDE.md"

    root = Path(ctx.cwd or os.getcwd())
    target = root / fname

    facts = project.scan(root)
    section = _render(facts)

    try:
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        merged = _merge_section(existing, section)
        _write_atomic(target, merged)
    except Exception:
        return Result(action="message",
                      payload=f"[cpl init] Could not write {target}. "
                              f"Check permissions and try again.")

    lines = ["🧭 cpl init",
             "",
             f"  Wrote project context to {fname} (cpl-managed section).",
             f"  Project: {facts.get('name', '?')} · "
             f"Stack: {', '.join(facts.get('languages') or []) or 'n/a'}",
             ""]
    if quick:
        lines.append("  Baseline written. Re-run `/cpl init` (no --quick) to let "
                     "cpl enrich it with architecture notes.")
    else:
        lines += [
            "ENRICH: Now read this repo and improve the section between the "
            f"`{_START}` and `{_END}` markers in {fname}: add a short, concise "
            "architecture / conventions / gotchas note (a few lines — this file "
            "loads every session). Edit ONLY the text between those markers; "
            "leave the factual lines and everything outside the markers intact."]
    return Result(action="message", payload="\n".join(lines),
                  meta={"skill": "init", "quick": quick})


SKILL = Skill(name="init", run=run, command="init")
