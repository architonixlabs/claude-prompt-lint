"""profile skill — /cpl profile

Reads the local prompt log and surfaces your *recurring* prompt weaknesses over
time: which issue categories show up most, how your flag rate trends, and a
concrete tip for your top weakness. Everything is local; categories are stable
tags, never your prompt text.
"""

from __future__ import annotations

from collections import Counter

from cpl.registry import Context, Result, Skill
from cpl.shared import log

# Human-readable labels + a tip for each stable category tag emitted by rules.py.
_CATEGORY_INFO = {
    "no_anchor": (
        "No concrete anchor",
        "Lead with a file path, function name, or the exact error text.",
    ),
    "no_acceptance_criteria": (
        "No acceptance criteria",
        "End prompts with what 'done' looks like — a test that passes, or the "
        "expected output.",
    ),
    "dangling_reference": (
        "Dangling 'it/this/that'",
        "Replace pronouns with the actual file or symbol you mean.",
    ),
    "vague_verb": (
        "Vague verb, no object",
        "Pair 'improve/optimize/clean up' with a target and a metric.",
    ),
    "long_ramble": (
        "Long ramble, buried ask",
        "Put the one-line ask first, context after.",
    ),
}

_MIN_SAMPLES = 5


def run(ctx: Context) -> Result:
    if ctx.log_path is None or not ctx.log_path.is_file():
        return Result(
            action="message",
            payload="[cpl profile] No prompt log yet. Use Claude Code for a bit; "
                    "the gate records your prompt patterns locally as you go.",
        )

    records = [r for r in log.iter_records(ctx.log_path) if r.get("event") == "gate"]
    if len(records) < _MIN_SAMPLES:
        return Result(
            action="message",
            payload=f"[cpl profile] Only {len(records)} prompt(s) logged so far — "
                    f"need at least {_MIN_SAMPLES} to spot trends. Check back later.",
        )

    total = len(records)
    flagged = [r for r in records if r.get("action") in ("block", "inject")]
    cat_counter: Counter = Counter()
    for r in records:
        for c in r.get("categories", []) or []:
            cat_counter[c] += 1

    lines = [
        "🧭 cpl profile — your recurring prompt weaknesses",
        "",
        f"  Prompts analyzed : {total}",
        f"  Flagged          : {len(flagged)} ({len(flagged) / total * 100:.0f}%)",
        "",
    ]

    if not cat_counter:
        lines.append("  No specific weaknesses recorded — your prompts look clean. 🎯")
        return Result(action="message", payload="\n".join(lines))

    lines.append("  Most common issues (share of all prompts):")
    for cat, n in cat_counter.most_common():
        label = _CATEGORY_INFO.get(cat, (cat, ""))[0]
        pct = n / total * 100
        bar = "█" * max(1, round(pct / 5))
        lines.append(f"    {label:<24} {bar} {pct:4.0f}%  ({n})")

    # Spotlight the single biggest recurring weakness.
    top_cat, top_n = cat_counter.most_common(1)[0]
    label, tip = _CATEGORY_INFO.get(top_cat, (top_cat, ""))
    lines += [
        "",
        f"  👉 Your top recurring weakness: {label} "
        f"({top_n / total * 100:.0f}% of prompts).",
    ]
    if tip:
        lines.append(f"     Fix: {tip}")

    return Result(action="message", payload="\n".join(lines))


SKILL = Skill(name="profile", run=run, command="profile")
