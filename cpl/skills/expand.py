"""expand skill — /cpl expand <prompt>

Takes a terse prompt and scaffolds it into a structured one with the sections a
good engineering prompt needs — Task, Anchor, Constraints, Done-when — leaving
[bracketed placeholders] for whatever you didn't specify. Unlike `rewrite`
(which tightens wording), `expand` adds *structure* you can fill in.

Model-backed when the local model is enabled; otherwise emits a static
scaffold seeded with your prompt.
"""

from __future__ import annotations

from cpl.registry import Context, Result, Skill
from cpl.shared import model_client, rules

_EXPAND_TIMEOUT_MS = 8000

_EXPAND_SYSTEM = (
    "You expand a terse software-engineering prompt into a structured one. "
    "Output exactly these four labelled lines, filling in what the user gave and "
    "leaving a short [bracketed placeholder] for anything they did not specify. "
    "Do NOT invent specifics. Format:\n"
    "Task: <the core ask in one line>\n"
    "Anchor: <file/function/error to act on, or [name the file/symbol]>\n"
    "Constraints: <what to preserve / avoid, or [constraints?]>\n"
    "Done when: <how success is verified, or [expected output / passing test]>\n"
    "Return only those four lines."
)


def _static_scaffold(target: str) -> str:
    return "\n".join(
        [
            "🧱 cpl expand",
            "",
            f"  Original : {target}",
            "",
            "  Fill the brackets, then send:",
            "",
            f"    Task       : {target}",
            "    Anchor     : [file path / function / error text to act on]",
            "    Constraints: [what must NOT change; what to avoid]",
            "    Done when  : [expected output, or a test that should pass]",
        ]
    )


def run(ctx: Context) -> Result:
    target = (ctx.args or ctx.prompt or "").strip()
    if not target:
        return Result(
            action="message",
            payload="[cpl expand] Usage: /cpl expand <your terse prompt>",
        )

    cfg = ctx.config or {}

    if cfg.get("use_model", False):
        timeout = max(int(cfg.get("model_timeout_ms", 1500)), _EXPAND_TIMEOUT_MS)
        full = (
            f"{_EXPAND_SYSTEM}\n\n"
            f"TERSE PROMPT:\n<<<\n{target}\n>>>\n\nSTRUCTURED PROMPT:"
        )
        expanded = model_client.generate(
            full,
            endpoint=cfg.get("model_endpoint"),
            model=cfg.get("model"),
            timeout_ms=timeout,
        )
        if expanded:
            lines = ["🧱 cpl expand", "", f"  Original : {target}", "",
                     "  Structured (fill any [placeholders]):", ""]
            for ln in expanded.splitlines() or [expanded]:
                lines.append(f"    {ln}")
            return Result(action="message", payload="\n".join(lines),
                          meta={"source": "model"})
        # fall through to the static scaffold on model failure

    # Rules-only static scaffold (also notes what's already present).
    rules.evaluate(target)  # keeps behavior parallel; result unused here
    return Result(action="message", payload=_static_scaffold(target),
                  meta={"source": "scaffold"})


SKILL = Skill(name="expand", run=run, command="expand")
