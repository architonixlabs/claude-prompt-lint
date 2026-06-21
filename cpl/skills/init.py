"""init skill — /cpl init [--quick]

Writes a concise, cpl-managed project-context section into the project-root
CLAUDE.md (which Claude Code loads natively every session — zero per-turn token
cost). cpl fills a deterministic factual baseline; unless --quick, the command
layer (Claude) then enriches the section in place.

Merge-safe: only the text between the cpl markers is touched. Idempotent.
Fail-safe: reports a clear message on a write error; never raises.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from cpl.registry import Context, Result, Skill
from cpl.shared import project

_START = "<!-- cpl:context:start -->"
_END = "<!-- cpl:context:end -->"
_FP = "<!-- cpl:fp:"   # embedded baseline fingerprint -> drift detection


def _fingerprint(facts) -> str:
    """Stable short hash of the repo's STRUCTURAL facts.

    Embedded in the written section so a later `/cpl init` can tell whether the
    repo has drifted from the recorded context — the freshness signal a one-shot
    generator (like the native /init) doesn't give you.

    Deliberately excludes `languages`: writing CLAUDE.md adds a Markdown file,
    which shifts the language counts and would make every re-run look like drift
    (a self-write feedback loop). manifests/commands/layout/git/entry_points/name
    capture real structural change and are invariant to cpl's own write. A new
    language almost always arrives with a new manifest or dir, so it's still
    caught.
    """
    keys = ("name", "manifests", "commands", "layout", "git", "entry_points")
    subset = {k: facts.get(k) for k in keys}
    try:
        canon = json.dumps(subset, sort_keys=True, default=str)
    except Exception:
        canon = repr(subset)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:12]


def _existing_fp(existing: str) -> str:
    """Pull the prior fingerprint out of an existing CLAUDE.md, or '' if none."""
    i = existing.find(_FP)
    if i == -1:
        return ""
    j = existing.find("-->", i)
    if j == -1:
        return ""
    return existing[i + len(_FP):j].strip()


def _merge_section(existing: str, section: str) -> str:
    """Replace the delimited cpl section in `existing`, else append it.

    Replaces from the first start to the first end after it, so stray
    end-markers in user prose below the section are never consumed. Pure and
    total."""
    if not existing.strip():
        return section
    i = existing.find(_START)
    if i == -1:
        return existing.rstrip() + "\n\n" + section + "\n"
    j = existing.find(_END, i)   # first end AFTER the start — never eats user prose below
    if j == -1:
        return existing.rstrip() + "\n\n" + section + "\n"
    return existing[:i] + section + existing[j + len(_END):]


def _render(facts, fingerprint: str = "") -> str:
    fp = fingerprint or _fingerprint(facts)
    lines = [_START,
             f"{_FP}{fp} -->",
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
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def run(ctx: Context) -> Result:
    if ctx.event != "command":
        return Result(action="pass")

    args = (ctx.args or "").strip()
    quick = "--quick" in args.split()

    cfg = ctx.config or {}
    init_cfg = cfg.get("init", {}) if isinstance(cfg.get("init"), dict) else {}
    fname = init_cfg.get("claude_md", "CLAUDE.md") or "CLAUDE.md"

    root = Path(ctx.cwd or os.getcwd())
    target = root / fname

    facts = project.scan(root)
    fp = _fingerprint(facts)
    section = _render(facts, fp)

    try:
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        prior_fp = _existing_fp(existing)
        merged = _merge_section(existing, section)
        _write_atomic(target, merged)
    except Exception:
        return Result(action="message",
                      payload=f"[cpl init] Could not write {target}. "
                              f"Check permissions and try again.")

    # Freshness signal — the thing a one-shot generator can't give you.
    if not prior_fp:
        drift = "  Status: first run — baseline context written."
    elif prior_fp == fp:
        drift = "  Status: ✓ up to date — repo matches the recorded context (no drift)."
    else:
        drift = ("  Status: ↻ refreshed — the repo changed since the last "
                 "`/cpl init`; baseline facts updated.")

    lines = ["🧭 cpl init",
             "",
             f"  Wrote project context to {fname} (cpl-managed section).",
             f"  Project: {facts.get('name', '?')} · "
             f"Stack: {', '.join(facts.get('languages') or []) or 'n/a'}",
             drift,
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
