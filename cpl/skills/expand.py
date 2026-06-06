"""expand skill — /cpl expand  (v1.x differentiator, stub)

Will scaffold a terse prompt with the structure it's missing (anchor,
criteria, constraints) so you can fill the blanks. Disabled by default.
"""

from __future__ import annotations

from cpl.registry import Context, Result, Skill


def run(ctx: Context) -> Result:
    return Result(
        action="message",
        payload="[cpl expand] Coming in v1.x — scaffold a terse prompt with the "
                "structure it's missing.",
    )


SKILL = Skill(name="expand", run=run, command="expand")
