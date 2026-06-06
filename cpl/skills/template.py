"""template skill — /cpl template <name>  (v1.x differentiator, stub)

Will emit reusable prompt templates (bugfix, refactor, migration, …) from
the templates/ directory. Disabled by default. A minimal lookup is wired so
the templates ship and work once enabled.
"""

from __future__ import annotations

import os
from pathlib import Path

from cpl.registry import Context, Result, Skill


def _templates_dir() -> Path:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        return Path(root) / "templates"
    return Path(__file__).resolve().parents[2] / "templates"


def run(ctx: Context) -> Result:
    name = (ctx.args or "").strip().split()[0] if (ctx.args or "").strip() else ""
    tdir = _templates_dir()

    if not name:
        available = []
        if tdir.is_dir():
            available = sorted(p.stem for p in tdir.glob("*.md"))
        listing = ", ".join(available) if available else "(none found)"
        return Result(
            action="message",
            payload=f"[cpl template] Usage: /cpl template <name>. Available: {listing}",
        )

    path = tdir / f"{name}.md"
    if not path.is_file():
        return Result(
            action="message",
            payload=f"[cpl template] No template named '{name}' in {tdir}.",
        )
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return Result(
            action="message",
            payload=f"[cpl template] Could not read template '{name}'.",
        )
    return Result(action="message", payload=content)


SKILL = Skill(name="template", run=run, command="template")
