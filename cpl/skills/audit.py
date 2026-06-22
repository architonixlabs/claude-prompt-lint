"""audit skill — /cpl audit [N]

A local, metadata-only readout of what cpl caught at the boundary: secret masks
on prompts (the `mask` skill) and PreToolUse interventions (the `guard` skill).
It makes the security claim *inspectable* — "here is every secret cpl stopped
from leaving this machine" — without ever recording a secret value or where it
lives. Kinds and timestamps only; the log it reads stores nothing more.
"""

from __future__ import annotations

from collections import Counter

from cpl.registry import Context, Result, Skill
from cpl.shared import log

# Actions that mean cpl actually intervened on a real secret/PII finding.
_CATCH_ACTIONS = {"block", "inject", "deny", "ask", "warn"}
_SECURITY_EVENTS = {"mask", "guard"}


def _kinds_of(rec) -> list:
    ks = rec.get("kinds") or []
    return [ks] if isinstance(ks, str) else list(ks)


def run(ctx: Context) -> Result:
    if ctx.log_path is None or not ctx.log_path.is_file():
        return Result(action="message",
                      payload="[cpl audit] No log yet — nothing to audit.")

    arg = (ctx.args or "").strip()
    n = max(1, min(int(arg), 500)) if arg.isdigit() else 20

    recs = [r for r in log.read_all(ctx.log_path)
            if r.get("event") in _SECURITY_EVENTS
            and r.get("action") in _CATCH_ACTIONS]

    if not recs:
        return Result(action="message", payload=(
            "🔍 cpl audit — no secrets caught at the boundary yet.\n"
            "  (Either nothing sensitive has been sent, or cpl hasn't seen one.)"))

    by_source = Counter(r.get("event") for r in recs)
    kinds = Counter()
    for r in recs:
        for k in _kinds_of(r):
            kinds[k] += 1

    lines = [
        "🔍 cpl audit — secrets caught at the boundary (local, metadata only)",
        "",
        f"  Total catches : {len(recs)}",
        f"  By source     : prompt-mask {by_source.get('mask', 0)} · "
        f"tool-guard {by_source.get('guard', 0)}",
        "  Top kinds     : " + (", ".join(f"{k}×{c}"
                                          for k, c in kinds.most_common(6)) or "n/a"),
        "",
        f"  Most recent {min(n, len(recs))}:",
    ]
    for r in recs[-n:]:
        ts = (r.get("ts", "") or "")[:19].replace("T", " ")
        src = r.get("event", "?")
        where = r.get("tool") or ("prompt" if src == "mask" else "?")
        act = r.get("action", "?")
        ks = ", ".join(_kinds_of(r)) or "-"
        lines.append(f"    {ts:<19}  {src:<5}  {act:<5}  {where:<8}  {ks}")

    lines += [
        "",
        "  (No secret values or file paths are ever stored — detector kinds only.)",
    ]
    return Result(action="message", payload="\n".join(lines))


SKILL = Skill(name="audit", run=run, command="audit")
