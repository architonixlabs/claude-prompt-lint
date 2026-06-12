"""explain skill — /cpl explain <prompt>

Runs the same Tier 1 (and optional Tier 2) analysis the gate uses, but
instead of gating, prints a detailed breakdown of what would be flagged and
why. Useful for understanding a block, or dry-running a prompt before sending.
"""

from __future__ import annotations

from cpl.registry import Context, Result, Skill
from cpl.shared import model_client, rules

# `explain` is an interactive command, not the latency-critical gate. Give the
# model a generous budget (matching `rewrite`/`expand`) so a cold Ollama model
# doesn't spuriously report "unavailable" the way the gate's 1.5s would.
_EXPLAIN_TIMEOUT_MS = 8000


def run(ctx: Context) -> Result:
    target = (ctx.args or ctx.prompt or "").strip()
    if not target:
        return Result(
            action="message",
            payload="[cpl explain] Usage: /cpl explain <your prompt>",
        )

    r1 = rules.evaluate(target)
    score = min(100, r1.penalty)

    lines = [
        "🔍 cpl explain",
        "",
        f"  Prompt   : {target[:200]}{'…' if len(target) > 200 else ''}",
        f"  Anchors  : {r1.anchors} (file paths, symbols, errors, quotes, urls)",
        f"  Tier-1 score : {score}/100 (higher = weaker)",
        "",
    ]

    if r1.issues:
        lines.append("  Issues:")
        for it in r1.issues:
            lines.append(f"    • {it}")
    else:
        lines.append("  Issues: none from Tier-1 rules. Looks specific.")
    lines.append("")

    if r1.suggestions:
        lines.append("  Suggestions:")
        for sg in r1.suggestions:
            lines.append(f"    → {sg}")
        lines.append("")

    # Optional Tier 2 detail.
    cfg = ctx.config
    if cfg.get("use_model", False):
        timeout = max(int(cfg.get("model_timeout_ms", 1500)), _EXPLAIN_TIMEOUT_MS)
        verdict = model_client.evaluate(
            target,
            endpoint=cfg.get("model_endpoint"),
            model=cfg.get("model"),
            timeout_ms=timeout,
        )
        if verdict is None:
            lines.append("  Tier-2 model: unavailable (fail-open — prompt would pass).")
        else:
            lines.append(
                f"  Tier-2 model : score {verdict['score']}/100, "
                f"pass={verdict['pass']}"
            )
            for it in verdict.get("issues", []):
                lines.append(f"    • {it}")
            for sg in verdict.get("suggestions", []):
                lines.append(f"    → {sg}")

    return Result(action="message", payload="\n".join(lines).rstrip())


SKILL = Skill(name="explain", run=run, command="explain")
