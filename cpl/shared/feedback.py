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

    # Offer a fix, don't just scold: point at the tool that tightens it for you.
    lines.append("Tighten it for me: `/cpl rewrite <your prompt>`")
    lines.append(
        f"Send as-is: prefix your prompt with `{bypass_prefix}` to bypass the gate."
    )
    return "\n".join(lines).rstrip()


def format_warn_inject(
    score: int, issues: List[str], suggestions: List[str]
) -> str:
    """Coach the assistant (warn mode injects this into context; prompt proceeds).

    The old wording scolded the *user* ("your prompt is weak"), which is
    ignorable at best and nagging at worst. This text instead briefs the
    *assistant* on what's thin and how to handle it gracefully — confirm the
    missing piece in one line, or proceed on a stated assumption. It is
    deliberately bounded ("one question at most — don't stall") so it works
    with an increasingly capable agent rather than turning it into an
    interrogator. Only fires when the gate already flagged the prompt.
    """
    issues = _dedupe(issues)
    top = issues[0] if issues else "the prompt may be under-specified"
    return (
        f"[{_BRAND}] Note for the assistant — the user's prompt scored "
        f"{score}/100 on local prompt-quality checks ({top}). Before any large "
        f"or irreversible change, confirm the specific target (file, symbol, or "
        f"expected outcome) in one short question, or proceed and state the "
        f"assumption you're acting on. At most one clarifying question — "
        f"don't stall on a workable prompt."
    )


def format_mask_block(findings, masked_prompt: str) -> str:
    """Block message: which secrets fired + the prompt already masked to resend."""
    lines = ["🔒 cpl blocked — your prompt contains data that shouldn't be sent:",
             ""]
    seen = set()
    for f in findings:
        if f.severity != "block" or f.kind in seen:
            continue
        seen.add(f.kind)
        lines.append(f"  • {f.label}: {f.preview}")
    lines += ["",
              "Send a cleaned version (copy & paste this):",
              ""]
    for ln in masked_prompt.splitlines() or [masked_prompt]:
        lines.append(f"  {ln}")
    lines += ["",
              "If a match is a false positive, add it to mask.allowlist in "
              "~/.cpl/config.json."]
    return "\n".join(lines).rstrip()


def format_mask_warn(findings) -> str:
    """Compact warn note for PII (prompt still proceeds)."""
    kinds = []
    seen = set()
    for f in findings:
        if f.kind not in seen:
            seen.add(f.kind)
            kinds.append(f.label.lower())
    listed = ", ".join(kinds) if kinds else "personal data"
    return f"[{_BRAND}] heads-up: your prompt appears to contain {listed}."
