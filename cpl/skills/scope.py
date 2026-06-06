"""scope skill — /cpl scope  (v1.x differentiator, stub)

Will check that files/symbols referenced in a prompt actually exist in the
repo, catching typos and stale references. Disabled by default.
"""

from __future__ import annotations

from cpl.registry import Context, Result, Skill


def run(ctx: Context) -> Result:
    return Result(
        action="message",
        payload="[cpl scope] Coming in v1.x — verify referenced files/symbols "
                "exist in the repo.",
    )


SKILL = Skill(name="scope", run=run, command="scope")
