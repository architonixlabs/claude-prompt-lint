"""Secret / PII detection for the mask skill.

Pure-stdlib regex heuristics. Tuned for LOW false positives because the secret
path BLOCKS the prompt. Fully fail-safe: any error yields no findings, so a
scanner bug never blocks a legitimate prompt (fail-open).

Never returns or logs a full secret value — `Finding.preview` is always masked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

SECRET = "secret"
PII = "pii"
BLOCK = "block"
WARN = "warn"


@dataclass
class Finding:
    kind: str
    label: str
    category: str   # SECRET | PII
    severity: str   # BLOCK | WARN
    start: int
    end: int
    preview: str    # masked form of the matched text


# (kind, label, regex, category, severity). Order matters only for display.
_BUILTINS: List[Tuple[str, str, "re.Pattern", str, str]] = [
    ("aws_access_key", "AWS access key",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), SECRET, BLOCK),
    ("google_api_key", "Google API key",
     re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), SECRET, BLOCK),
    ("anthropic_key", "Anthropic API key",
     re.compile(r"\bsk-ant-[0-9A-Za-z\-_]{20,}\b"), SECRET, BLOCK),
    ("openai_key", "OpenAI API key",
     re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}\b"), SECRET, BLOCK),
    ("github_token", "GitHub token",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), SECRET, BLOCK),
    ("slack_token", "Slack token",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), SECRET, BLOCK),
    ("stripe_key", "Stripe key",
     re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"), SECRET, BLOCK),
    ("private_key", "Private key block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
     SECRET, BLOCK),
    ("jwt", "JWT",
     re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
     SECRET, BLOCK),
    ("bearer_token", "Bearer token",
     re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}"), SECRET, BLOCK),
    ("secret_assignment", "Secret assignment",
     re.compile(r"(?i)\b(?:api[_-]?key|secret|access[_-]?token|client[_-]?secret|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9\-_./+]{8,}"),
     SECRET, BLOCK),
    ("password_assignment", "Password assignment",
     re.compile(r"(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"]{6,}"),
     SECRET, BLOCK),
    ("connection_string", "Connection string with credentials",
     re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://[^:\s/]+:[^@\s/]+@"),
     SECRET, BLOCK),
    ("email", "Email address",
     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), PII, WARN),
    ("ipv4", "IP address",
     re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
     PII, WARN),
    ("phone", "Phone number",
     re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
     PII, WARN),
    ("ssn", "US SSN",
     re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), PII, WARN),
    # credit_card handled specially (Luhn) in scan().
]

_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_ok(digits: str) -> bool:
    try:
        nums = [int(c) for c in digits]
    except Exception:
        return False
    if not (13 <= len(nums) <= 19):
        return False
    total, parity = 0, len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _preview(kind: str, value: str) -> str:
    if kind == "private_key":
        return "«PRIVATE KEY redacted»"
    if kind == "email":
        name, _, dom = value.partition("@")
        d = dom.split(".")
        return f"{name[:1]}…@{d[0][:1]}….{d[-1]}" if "@" in value else "…@…"
    v = value.strip()
    if len(v) <= 8:
        return (v[:1] + "…") if v else "…"
    return f"{v[:4]}…{v[-4:]}"


def _allowlist(cfg: Optional[Dict]):
    mask = (cfg or {}).get("mask", {}) if isinstance(cfg, dict) else {}
    pats = []
    for item in mask.get("allowlist", []) or []:
        s = str(item)
        if not s:
            continue
        try:
            pats.append(re.compile(s))
        except Exception:
            pats.append(re.compile(re.escape(s)))   # treat as literal
    return pats


def _custom(cfg: Optional[Dict]):
    mask = (cfg or {}).get("mask", {}) if isinstance(cfg, dict) else {}
    out = []
    for item in mask.get("custom_patterns", []) or []:
        if not isinstance(item, dict):
            continue
        name, rx = item.get("name"), item.get("regex")
        sev = item.get("severity", BLOCK)
        if not name or not rx:
            continue
        try:
            pat = re.compile(rx)
        except Exception:
            continue   # bad regex → skip, never raise
        cat = SECRET if sev == BLOCK else PII
        out.append((str(name), str(name), pat, cat, BLOCK if sev == BLOCK else WARN))
    return out


def scan(text: str, cfg: Optional[Dict] = None) -> List[Finding]:
    """Return findings sorted by position, overlaps removed, allowlisted dropped.

    Fail-safe: any error returns []."""
    try:
        if not isinstance(text, str) or not text:
            return []
        allow = _allowlist(cfg)
        raw: List[Finding] = []
        for kind, label, pat, cat, sev in (_BUILTINS + _custom(cfg)):
            for m in pat.finditer(text):
                val = m.group(0)
                raw.append(Finding(kind, label, cat, sev, m.start(), m.end(),
                                   _preview(kind, val)))
        # Credit cards with Luhn validation.
        for m in _CARD_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if _luhn_ok(digits):
                raw.append(Finding("credit_card", "Credit card", PII, WARN,
                                   m.start(), m.end(), _preview("credit_card", m.group(0))))
        # Drop allowlisted matches.
        def allowed(f: Finding) -> bool:
            seg = text[f.start:f.end]
            return any(a.search(seg) for a in allow)
        raw = [f for f in raw if not allowed(f)]
        # Sort, then drop findings fully contained in an earlier (longer) one.
        raw.sort(key=lambda f: (f.start, -(f.end - f.start)))
        kept: List[Finding] = []
        last_end = -1
        for f in raw:
            if f.start >= last_end:
                kept.append(f)
                last_end = f.end
        return kept
    except Exception:
        return []


def mask_text(text: str, findings: List[Finding]) -> str:
    """Replace each finding span with its masked preview (right-to-left)."""
    try:
        if not isinstance(text, str):
            return ""
        out = text
        for f in sorted(findings, key=lambda f: f.start, reverse=True):
            out = out[:f.start] + f.preview + out[f.end:]
        return out
    except Exception:
        return text if isinstance(text, str) else ""


def has_block(findings: List[Finding]) -> bool:
    return any(f.severity == BLOCK for f in (findings or []))


def has_warn(findings: List[Finding]) -> bool:
    return any(f.severity == WARN for f in (findings or []))
