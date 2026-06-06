"""stats skill — /cpl stats

Reads the local prompt log and reports gated/passed counts plus a rough
estimate of tokens saved. The estimate is intentionally a heuristic (Part J
open decision #4): rough is fine for v1, and it's labelled as such.
"""

from __future__ import annotations

from collections import Counter

from cpl.registry import Context, Result, Skill
from cpl.shared import log

# Rough heuristic: each blocked weak prompt saves ~one clarification round-trip.
# A round-trip ≈ a short model reply asking for specifics + the user's resend.
# We deliberately under-claim to stay credible.
_TOKENS_PER_BLOCK = 350


def run(ctx: Context) -> Result:
    if ctx.log_path is None or not ctx.log_path.is_file():
        return Result(
            action="message",
            payload="[cpl stats] No prompt log yet. The gate writes one as you work.",
        )

    records = [r for r in log.iter_records(ctx.log_path) if r.get("event") == "gate"]
    if not records:
        return Result(
            action="message",
            payload="[cpl stats] No gate activity logged yet.",
        )

    actions = Counter(r.get("action", "pass") for r in records)
    tiers = Counter(r.get("tier", "?") for r in records)

    total = len(records)
    blocked = actions.get("block", 0)
    warned = actions.get("inject", 0)
    passed = actions.get("pass", 0)
    flagged = blocked + warned

    est_tokens = blocked * _TOKENS_PER_BLOCK

    lines = [
        "📊 cpl stats",
        "",
        f"  Prompts seen      : {total}",
        f"  Passed            : {passed}",
        f"  Flagged (warn)    : {warned}",
        f"  Blocked           : {blocked}",
        "",
        f"  Flag rate         : {(flagged / total * 100):.1f}%"
        if total else "  Flag rate         : n/a",
        "",
        "  Resolved by tier:",
    ]
    for tier, n in tiers.most_common():
        lines.append(f"    {tier:<18}: {n}")

    lines += [
        "",
        f"  Est. tokens saved : ~{est_tokens:,} "
        f"(rough: {blocked} blocks × ~{_TOKENS_PER_BLOCK}/clarification)",
        "",
        "  (Estimate is a heuristic — see README. Only hard blocks count.)",
    ]

    return Result(action="message", payload="\n".join(lines))


SKILL = Skill(name="stats", run=run, command="stats")
