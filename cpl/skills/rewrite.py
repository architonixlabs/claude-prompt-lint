"""rewrite skill — /cpl rewrite <prompt>

Returns a tightened version of the prompt for the user to copy.

Two paths:
  * If the local model is enabled, it produces analysis the command layer
    (Claude) uses to author a concrete rewrite.
  * Rules-only, it emits a structured scaffold highlighting the missing
    pieces (anchor, acceptance criteria, constraints) so the user can fill
    them in. We never silently send a rewritten prompt — the user copies it.
"""

from __future__ import annotations

from cpl.registry import Context, Result, Skill
from cpl.shared import rules


def run(ctx: Context) -> Result:
    target = (ctx.args or ctx.prompt or "").strip()
    if not target:
        return Result(
            action="message",
            payload="[cpl rewrite] Usage: /cpl rewrite <your prompt>",
        )

    r1 = rules.evaluate(target)

    missing = []
    if r1.anchors == 0:
        missing.append(
            "Anchor — name the file/symbol/error "
            "(e.g. `auth.py`, `parseToken()`, the exact error text)."
        )
    issues_lower = " ".join(r1.issues).lower()
    if "acceptance criteria" in issues_lower:
        missing.append(
            "Acceptance criteria — what 'done' looks like "
            "(expected output, a test that passes)."
        )
    if "dangling" in issues_lower:
        missing.append(
            "Concrete referent — replace 'it/this/that' with the actual thing."
        )

    lines = [
        "✍️  cpl rewrite",
        "",
        f"  Original : {target}",
        "",
    ]

    if not missing:
        lines.append("  This prompt already looks specific. Minor tightening only:")
        lines.append(f"    {target}")
    else:
        lines.append("  Add the missing pieces below, then send:")
        lines.append("")
        lines.append("  ┌─ tightened prompt skeleton ─────────────────────────")
        lines.append(f"  │ {target}")
        lines.append("  │")
        for m in missing:
            lines.append(f"  │ + {m}")
        lines.append("  └─────────────────────────────────────────────────────")

    return Result(
        action="message",
        payload="\n".join(lines),
        score=min(100, r1.penalty),
        issues=list(r1.issues),
        suggestions=list(r1.suggestions),
        meta={"missing": missing},
    )


SKILL = Skill(name="rewrite", run=run, command="rewrite")
