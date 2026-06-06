"""profile skill — /cpl profile  (v1.x differentiator, stub)

Will analyze the prompt log over time to surface your recurring weaknesses
(e.g. "you omit acceptance criteria 60% of the time"). Disabled by default.
"""

from __future__ import annotations

from cpl.registry import Context, Result, Skill


def run(ctx: Context) -> Result:
    return Result(
        action="message",
        payload="[cpl profile] Coming in v1.x — recurring prompt-weakness trends "
                "from your local log.",
    )


SKILL = Skill(name="profile", run=run, command="profile")
