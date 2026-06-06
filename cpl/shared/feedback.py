"""Render gate verdicts into user-facing feedback text.

Kept deliberately compact: this text is shown to the user when a prompt is
blocked or warned. It should be skimmable in under two seconds.
"""

from __future__ import annotations

from typing import List

_BRAND = "cpl"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def format_block(
    score: int,
    issues: List[str],
    suggestions: List[str],
    bypass_prefix: str = "!!",
    mode: str = "block",
) -> str:
    """Build the message shown when the gate blocks or warns a prompt."""
    issues = _dedupe(issues)
    suggestions = _dedupe(suggestions)

    verb = "blocked" if mode == "block" else "flagged"
    header = f"⛔ Prompt {verb} by {_BRAND} (score {score}/100)"
    if mode != "block":
        header = f"⚠️  Prompt {verb} by {_BRAND} (score {score}/100)"

    lines = [header, ""]

    if issues:
        lines.append("What's weak:")
        for it in issues:
            lines.append(f"  • {it}")
        lines.append("")

    if suggestions:
        lines.append("Try this instead:")
        for sg in suggestions:
            lines.append(f"  → {sg}")
        lines.append("")

    lines.append(
        f"Send anyway: prefix your prompt with `{bypass_prefix}` to bypass the gate."
    )
    return "\n".join(lines).rstrip()


def format_warn_inject(
    score: int, issues: List[str], suggestions: List[str]
) -> str:
    """Compact note appended to context in warn mode (proceeds either way)."""
    issues = _dedupe(issues)
    top = issues[0] if issues else "prompt may be under-specified"
    hint = ""
    sugg = _dedupe(suggestions)
    if sugg:
        hint = f" Suggestion: {sugg[0]}"
    return f"[{_BRAND}] Prompt quality note (score {score}/100): {top}.{hint}"
