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
from cpl.shared import model_client, rules

# The rewrite generates more tokens than the gate's quick verdict, so give the
# model a more generous budget here than the gate's tight latency timeout.
_REWRITE_TIMEOUT_MS = 8000


def run(ctx: Context) -> Result:
    target = (ctx.args or ctx.prompt or "").strip()
    if not target:
        return Result(
            action="message",
            payload="[cpl rewrite] Usage: /cpl rewrite <your prompt>",
        )

    cfg = ctx.config or {}

    # Preferred path: ask the local model for a real tightened prompt.
    if cfg.get("use_model", False):
        timeout = max(int(cfg.get("model_timeout_ms", 1500)), _REWRITE_TIMEOUT_MS)
        tightened = model_client.rewrite(
            target,
            endpoint=cfg.get("model_endpoint"),
            model=cfg.get("model"),
            timeout_ms=timeout,
        )
        if tightened:
            lines = [
                "✍️  cpl rewrite",
                "",
                f"  Original  : {target}",
                "",
                "  Tightened (copy & edit any [placeholders]):",
                "",
            ]
            for ln in tightened.splitlines() or [tightened]:
                lines.append(f"    {ln}")
            return Result(
                action="message",
                payload="\n".join(lines),
                meta={"source": "model"},
            )
        # Model unavailable -> fall through to the rules-only scaffold.

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
