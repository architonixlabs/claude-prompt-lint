# Data Masking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-detect secrets (block) and PII (warn) on every prompt, with a paste-ready masked version on block and a `/cpl mask` helper.

**Architecture:** A new `cpl/shared/secrets.py` detection library feeds a new `cpl/skills/mask.py` skill that registers for BOTH the `UserPromptSubmit` hook (runs before `gate`) and the `/cpl mask` command. The platform can't rewrite prompts, so a blocked prompt's message carries the fully-masked prompt for the user to resend. Fail-open: a scanner bug never blocks a legit prompt.

**Tech Stack:** Python 3 standard library only (no pip deps). Tests use stdlib `unittest`, run from repo root with `python3`.

## Global Constraints

- **Zero dependencies.** Standard library only. No `requirements.txt`, no imports beyond stdlib.
- **Fail-open is sacred.** No code path reachable from the hook may raise/block due to an internal failure. A scanner exception → no findings → prompt passes.
- **Never persist a secret value.** Logs/debug store the detector `kind` only, never the matched text.
- **snake_case**, module docstrings explain "why". Commit messages: conventional prefix + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **Tests are stdlib `unittest`**, discovered via `python3 -m unittest discover -s tests`. The gate eval (`python3 eval/run_eval.py`) must stay at **FPR 0.0%**.
- Spec: `docs/superpowers/specs/2026-06-21-data-masking-design.md`. Branch: `feat/data-masking`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `cpl/shared/secrets.py` | Detection library: `Finding`, patterns, `scan`, `mask_text` | Create |
| `cpl/skills/mask.py` | `mask` skill: hook (block/warn) + `/cpl mask` command | Create |
| `cpl/shared/feedback.py` | `format_mask_block` + `format_mask_warn` renderers | Modify |
| `cpl/registry.py` | Add `"mask"` before `"gate"` in `_SKILL_MODULES` | Modify |
| `config/cpl.config.json` | `mask` config block + `"mask": true` in skills | Modify |
| `commands/cpl.md`, `README.md`, `CHANGELOG.md`, version files | Docs + release | Modify |
| `tests/test_secrets.py`, `tests/test_mask.py` | Unit tests | Create |

---

## Task 1: Detection library (`secrets.py`)

**Files:**
- Create: `cpl/shared/secrets.py`
- Test: `tests/test_secrets.py`

**Interfaces:**
- Produces:
  - `@dataclass Finding: kind:str, label:str, category:str, severity:str, start:int, end:int, preview:str`
  - `scan(text:str, cfg:dict|None=None) -> list[Finding]` — sorted by `start`, overlaps de-duped, allowlisted dropped, fail-safe (`[]` on error).
  - `mask_text(text:str, findings:list[Finding]) -> str` — replaces each finding span with its `preview`.
  - `has_block(findings) -> bool`, `has_warn(findings) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_secrets.py`:
```python
"""Tests for the secret/PII detection library (stdlib unittest)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.shared import secrets  # noqa: E402


class Detects(unittest.TestCase):
    def _kinds(self, text, cfg=None):
        return {f.kind for f in secrets.scan(text, cfg)}

    def test_aws_access_key_blocks(self):
        ks = self._kinds("my key is AKIAIOSFODNN7EXAMPLE here")
        self.assertIn("aws_access_key", ks)

    def test_openai_key(self):
        self.assertIn("openai_key",
                      self._kinds("token sk-abcdefghijklmnop0123456789"))

    def test_github_token(self):
        self.assertIn("github_token",
                      self._kinds("ghp_0123456789abcdefghijklmnopqrstuvwxyz"))

    def test_private_key(self):
        self.assertIn("private_key",
                      self._kinds("-----BEGIN RSA PRIVATE KEY-----\nMII..."))

    def test_jwt(self):
        jwt = "eyJhbGciOiJI.eyJzdWIiOiIxMjM0NTY.SflKxwRJSMeKKF2QT4"
        self.assertIn("jwt", self._kinds(f"here is a token {jwt}"))

    def test_secret_assignment(self):
        self.assertIn("secret_assignment",
                      self._kinds('api_key = "abcd1234efgh"'))

    def test_password_assignment(self):
        self.assertIn("password_assignment",
                      self._kinds("password: hunter2pass"))

    def test_connection_string(self):
        self.assertIn("connection_string",
                      self._kinds("postgres://user:s3cret@db.example.com/app"))

    def test_email_is_pii_warn(self):
        fs = secrets.scan("contact me at jane.doe@example.com please")
        self.assertEqual([f.severity for f in fs if f.kind == "email"], ["warn"])

    def test_ssn(self):
        self.assertIn("ssn", self._kinds("ssn 123-45-6789"))


class NoFalsePositives(unittest.TestCase):
    def _kinds(self, text):
        return {f.kind for f in secrets.scan(text)}

    def test_prose_is_clean(self):
        self.assertEqual(
            self._kinds("Refactor parseToken() in auth.py and add a test"), set())

    def test_git_sha_not_a_secret(self):
        self.assertEqual(self._kinds("see commit 4932ddb for the fix"), set())

    def test_uuid_not_a_secret(self):
        self.assertEqual(
            self._kinds("id 550e8400-e29b-41d4-a716-446655440000"), set())

    def test_non_card_16_digits_rejected_by_luhn(self):
        # 16 digits that fail Luhn must NOT be flagged as a credit card.
        self.assertNotIn("credit_card", self._kinds("order number 1234567812345678"))

    def test_valid_card_passes_luhn(self):
        self.assertIn("credit_card", self._kinds("card 4242 4242 4242 4242"))


class Behavior(unittest.TestCase):
    def test_mask_text_redacts_in_place(self):
        text = "key sk-abcdefghijklmnop0123456789 end"
        fs = secrets.scan(text)
        masked = secrets.mask_text(text, fs)
        self.assertNotIn("sk-abcdefghijklmnop0123456789", masked)
        self.assertIn("end", masked)

    def test_preview_never_contains_full_secret(self):
        fs = secrets.scan("ghp_0123456789abcdefghijklmnopqrstuvwxyz")
        self.assertTrue(fs)
        self.assertNotIn("0123456789abcdefghijklmnopqrstuvwxyz", fs[0].preview)

    def test_allowlist_drops_match(self):
        cfg = {"mask": {"allowlist": ["AKIAIOSFODNN7EXAMPLE"]}}
        self.assertEqual(secrets.scan("AKIAIOSFODNN7EXAMPLE", cfg), [])

    def test_custom_pattern_honored(self):
        cfg = {"mask": {"custom_patterns": [
            {"name": "acme_token", "regex": r"ACME-[0-9]{6}", "severity": "block"}]}}
        ks = {f.kind for f in secrets.scan("token ACME-123456", cfg)}
        self.assertIn("acme_token", ks)

    def test_bad_custom_regex_is_skipped(self):
        cfg = {"mask": {"custom_patterns": [
            {"name": "bad", "regex": "(", "severity": "block"}]}}
        # Must not raise; built-ins still work.
        self.assertIn("openai_key",
                      {f.kind for f in secrets.scan("sk-abcdefghijklmnop0123456789", cfg)})

    def test_scan_failsafe_on_bad_input(self):
        self.assertEqual(secrets.scan(None), [])  # type: ignore

    def test_has_block_and_has_warn(self):
        fs = secrets.scan("postgres://u:p@h/db and jane@example.com")
        self.assertTrue(secrets.has_block(fs))
        self.assertTrue(secrets.has_warn(fs))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_secrets -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cpl.shared.secrets'`

- [ ] **Step 3: Implement `cpl/shared/secrets.py`**

```python
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
        out = text
        for f in sorted(findings, key=lambda f: f.start, reverse=True):
            out = out[:f.start] + f.preview + out[f.end:]
        return out
    except Exception:
        return text


def has_block(findings: List[Finding]) -> bool:
    return any(f.severity == BLOCK for f in findings)


def has_warn(findings: List[Finding]) -> bool:
    return any(f.severity == WARN for f in findings)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_secrets -v`
Expected: PASS (all tests). If `test_non_card_16_digits_rejected_by_luhn` fails, confirm `1234567812345678` indeed fails Luhn (it does); if a prose test fails, tighten the offending pattern — do not loosen a test.

- [ ] **Step 5: Run the full suite + eval (no regressions)**

Run: `python3 -m unittest discover -s tests` then `python3 eval/run_eval.py`
Expected: all OK; eval FPR `0.0%`.

- [ ] **Step 6: Commit**

```bash
git add cpl/shared/secrets.py tests/test_secrets.py
git commit -m "feat(secrets): stdlib secret/PII detection library (block + warn)"
```

---

## Task 2: Feedback renderers

**Files:**
- Modify: `cpl/shared/feedback.py`
- Test: covered via Task 3's `tests/test_mask.py` (these are pure formatting helpers exercised there)

**Interfaces:**
- Consumes: `secrets.Finding`, `secrets.mask_text`
- Produces:
  - `format_mask_block(findings:list, masked_prompt:str) -> str`
  - `format_mask_warn(findings:list) -> str`

- [ ] **Step 1: Add the two renderers to `cpl/shared/feedback.py`**

Append to `cpl/shared/feedback.py` (the module already exists with `_BRAND = "cpl"`):
```python
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
        if f.severity == "warn" and f.kind not in seen:
            seen.add(f.kind)
            kinds.append(f.label.lower())
    listed = ", ".join(kinds) if kinds else "personal data"
    return f"[{_BRAND}] heads-up: your prompt appears to contain {listed}."
```

- [ ] **Step 2: Smoke-check it imports**

Run: `python3 -c "from cpl.shared import feedback; print(hasattr(feedback,'format_mask_block'), hasattr(feedback,'format_mask_warn'))"`
Expected: `True True`

- [ ] **Step 3: Commit**

```bash
git add cpl/shared/feedback.py
git commit -m "feat(feedback): mask block + PII warn renderers"
```

---

## Task 3: The `mask` skill (hook + command) + config + registry

**Files:**
- Create: `cpl/skills/mask.py`
- Modify: `cpl/registry.py` (add `"mask"` before `"gate"`)
- Modify: `config/cpl.config.json` (`mask` block + `"mask": true`)
- Test: `tests/test_mask.py`

**Interfaces:**
- Consumes: `secrets.scan/mask_text/has_block/has_warn`, `feedback.format_mask_block/format_mask_warn`, `Context`, `Result`, `Skill`, `log`.
- Produces: `SKILL = Skill(name="mask", run=run, hook="UserPromptSubmit", command="mask")`.

- [ ] **Step 1: Add the `mask` config block**

In `config/cpl.config.json`, add after `"expand": { ... },` and before `"skills"`:
```json
  "mask": {
    "enabled": true,
    "block_secrets": true,
    "warn_pii": true,
    "allowlist": [],
    "custom_patterns": []
  },
```
And in the `"skills"` object add `"mask": true,` (e.g. as the first entry).
Verify: `python3 -c "import json; json.load(open('config/cpl.config.json'))"` → exit 0.

- [ ] **Step 2: Register the skill before the gate**

In `cpl/registry.py`, change `_SKILL_MODULES` so `"mask"` comes first:
```python
_SKILL_MODULES = [
    "mask",
    "gate",
    "rewrite",
    "stats",
    "explain",
    "profile",
    "expand",
    "scope",
    "template",
]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_mask.py`:
```python
"""Tests for the mask skill (hook + command) — stdlib unittest."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.registry import Context  # noqa: E402
from cpl.skills import mask  # noqa: E402

_SECRET = "deploy with AKIAIOSFODNN7EXAMPLE to prod and restart the worker"
_PII = "email the report to jane.doe@example.com after the run finishes"


def _cfg(**over):
    base = {"mask": {"enabled": True, "block_secrets": True, "warn_pii": True,
                     "allowlist": [], "custom_patterns": []}}
    base.update(over)
    return base


def _hook(prompt, cfg):
    return mask.run(Context(prompt=prompt, config=cfg, event="UserPromptSubmit"))


class HookPath(unittest.TestCase):
    def test_secret_blocks(self):
        res = _hook(_SECRET, _cfg())
        self.assertEqual(res.action, "block")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", res.payload)  # never echo raw
        self.assertIn("cleaned version", res.payload.lower())

    def test_pii_warns(self):
        res = _hook(_PII, _cfg())
        self.assertEqual(res.action, "inject")

    def test_clean_passes(self):
        res = _hook("refactor parseToken() in auth.py and add a test", _cfg())
        self.assertEqual(res.action, "pass")

    def test_block_secrets_false_downgrades(self):
        res = _hook(_SECRET, _cfg(mask={"enabled": True, "block_secrets": False,
                                        "warn_pii": True}))
        self.assertEqual(res.action, "inject")   # warn, not block

    def test_disabled_passes(self):
        res = _hook(_SECRET, _cfg(mask={"enabled": False}))
        self.assertEqual(res.action, "pass")

    def test_bypass_prefix_still_blocks_secret(self):
        res = _hook("!! " + _SECRET, _cfg())
        self.assertEqual(res.action, "block")

    def test_log_records_kinds_not_values(self):
        p = Path(tempfile.mktemp(suffix=".jsonl"))
        try:
            mask.run(Context(prompt=_SECRET, config=_cfg(), log_path=p,
                             event="UserPromptSubmit"))
            body = p.read_text(encoding="utf-8") if p.exists() else ""
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", body)
            if body:
                self.assertIn("aws_access_key", body)
        finally:
            if p.exists():
                p.unlink()


class CommandPath(unittest.TestCase):
    def test_mask_command_redacts(self):
        res = mask.run(Context(prompt="", args=_SECRET, config=_cfg(),
                               event="command"))
        self.assertEqual(res.action, "message")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", res.payload)

    def test_mask_command_clean_text(self):
        res = mask.run(Context(prompt="", args="nothing secret here at all",
                               config=_cfg(), event="command"))
        self.assertEqual(res.action, "message")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_mask -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cpl.skills.mask'`

- [ ] **Step 5: Implement `cpl/skills/mask.py`**

```python
"""mask skill — secret/PII detection on every prompt + /cpl mask command.

Auto-runs on the UserPromptSubmit hook (registered before `gate`): secrets BLOCK
the prompt (the platform can't redact in place, so the block message carries the
prompt already masked, ready to resend), PII WARNs. Also exposes `/cpl mask
<text>` to redact text on demand.

Independent of the gate's enabled/mode. Fail-open: any error → pass.
Logs detector kinds only, never a secret value.
"""

from __future__ import annotations

from typing import Any, Dict

from cpl.registry import Context, Result, Skill
from cpl.shared import feedback, log, secrets


def _mask_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    m = cfg.get("mask") if isinstance(cfg, dict) else None
    return m if isinstance(m, dict) else {}


def _log(ctx: Context, action: str, findings) -> None:
    if ctx.log_path is None:
        return
    log.append(ctx.log_path, {
        "event": "mask",
        "action": action,
        "kinds": sorted({f.kind for f in findings}),  # kinds only, never values
    })


def _run_command(ctx: Context) -> Result:
    text = (ctx.args or ctx.prompt or "").strip()
    if not text:
        return Result(action="message",
                      payload="[cpl mask] Usage: /cpl mask <text to redact>")
    findings = secrets.scan(text, ctx.config)
    if not findings:
        return Result(action="message",
                      payload="🔒 cpl mask — nothing sensitive detected.")
    masked = secrets.mask_text(text, findings)
    return Result(action="message",
                  payload="🔒 cpl mask — redacted (copy & paste):\n\n" + masked)


def run(ctx: Context) -> Result:
    cfg = ctx.config or {}

    # Command path: /cpl mask <text>
    if ctx.event == "command":
        return _run_command(ctx)

    # Hook path.
    mcfg = _mask_cfg(cfg)
    if not mcfg.get("enabled", True):
        return Result(action="pass", meta={"skill": "mask", "reason": "disabled"})

    findings = secrets.scan(ctx.prompt, cfg)
    if not findings:
        return Result(action="pass", meta={"skill": "mask"})

    # Secrets → block (unless block_secrets is off, then they warn).
    if secrets.has_block(findings) and mcfg.get("block_secrets", True):
        masked = secrets.mask_text(ctx.prompt, findings)
        payload = feedback.format_mask_block(findings, masked)
        _log(ctx, "block", findings)
        return Result(action="block", payload=payload, meta={"skill": "mask"})

    # PII (or downgraded secrets) → warn.
    if mcfg.get("warn_pii", True) and (secrets.has_warn(findings)
                                       or secrets.has_block(findings)):
        payload = feedback.format_mask_warn(findings)
        _log(ctx, "inject", findings)
        return Result(action="inject", payload=payload, meta={"skill": "mask"})

    _log(ctx, "pass", findings)
    return Result(action="pass", meta={"skill": "mask"})


SKILL = Skill(name="mask", run=run, hook="UserPromptSubmit", command="mask")
```

- [ ] **Step 6: Run the mask tests**

Run: `python3 -m unittest tests.test_mask -v`
Expected: PASS (all). If `test_pii_warns` fails because a secret is also present, note `_PII` has only an email (no secret) — confirm the email regex matches.

- [ ] **Step 7: Full suite + eval + end-to-end dispatcher check**

Run:
```bash
python3 -m unittest discover -s tests
python3 eval/run_eval.py
CLAUDE_PLUGIN_ROOT="$(pwd)" bash -c 'printf "%s" "{\"prompt\":\"ship AKIAIOSFODNN7EXAMPLE now\"}" | python3 hooks/dispatcher.py --event UserPromptSubmit'
```
Expected: all tests OK; FPR 0.0%; the dispatcher prints a `{"decision":"block",...}` JSON whose reason mentions an AWS access key and does NOT contain the raw key. (On Windows PowerShell, run the dispatcher line via the Bash tool or set `$env:CLAUDE_PLUGIN_ROOT` and pipe the JSON.)

- [ ] **Step 8: Commit**

```bash
git add cpl/skills/mask.py cpl/registry.py config/cpl.config.json tests/test_mask.py
git commit -m "feat(mask): auto secret-block / PII-warn skill + /cpl mask command"
```

---

## Task 4: Docs, CHANGELOG, version bump

**Files:**
- Modify: `commands/cpl.md`, `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `cpl/__init__.py`

- [ ] **Step 1: `commands/cpl.md` — add the mask command row + a note**

Add a row to the command table:
```markdown
| `/cpl mask <text>` | Returns a redacted copy of text (secrets/PII masked) to paste back. |
```
And add under `## Behaviour notes`:
```markdown
- **Data masking is automatic.** Every prompt is scanned locally; a detected
  secret (API key, private key, connection string…) blocks the prompt before it
  is sent, and the block message includes the prompt already masked to resend.
  PII (emails, etc.) only warns. This runs even if the gate is off.
```

- [ ] **Step 2: `README.md` — add a Data masking section + config row**

After the "Prompt frameworks" subsection, add:
```markdown
### Data masking (automatic)

Every prompt is scanned **locally** for sensitive data before it leaves your
machine:

- **Secrets** (API keys, tokens, private keys, DB connection strings) **block**
  the prompt. Because a hook can't silently rewrite your prompt, the block
  message hands you the **prompt already masked** — paste it back and resend.
- **PII** (emails, phone numbers, IPs, cards, SSNs) only **warns**.
- **`/cpl mask <text>`** redacts text on demand.
- Tune under `"mask"` in `~/.cpl/config.json`: `block_secrets`, `warn_pii`, a
  `custom_patterns` list (`{name, regex, severity}`), and an `allowlist` for
  false positives. `!!` does **not** skip a secret block — use the allowlist for
  values you intend to send.
```
Add to the config table:
```markdown
| `mask` | (object) | `enabled`, `block_secrets`, `warn_pii`, `allowlist`, `custom_patterns` for data masking. |
```

- [ ] **Step 3: CHANGELOG — add the 1.4.0 entry**

At the top of `CHANGELOG.md` (above `## [1.3.0]`):
```markdown
## [1.4.0] — 2026-06-21

### Added
- **Data masking (automatic, local).** Every prompt is scanned for sensitive
  data before send: secrets (API keys, tokens, private keys, JWTs, connection
  strings) **block** the prompt — with a paste-ready masked version, since the
  platform can't silently rewrite prompts — and PII (email/phone/IP/card/SSN)
  **warns**. New `/cpl mask <text>` redacts on demand.
- **Config:** a `"mask"` block (`enabled`, `block_secrets`, `warn_pii`,
  `allowlist`, `custom_patterns`). Masking is independent of the gate; `!!` does
  not bypass a secret block (use the allowlist). Logs record detector kinds
  only, never secret values.

```

- [ ] **Step 4: Bump version to 1.4.0**

```bash
python3 - <<'PY'
import json, re, pathlib
p=pathlib.Path(".claude-plugin/plugin.json"); d=json.loads(p.read_text(encoding="utf-8")); d["version"]="1.4.0"; p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
p=pathlib.Path(".claude-plugin/marketplace.json"); d=json.loads(p.read_text(encoding="utf-8")); d["metadata"]["version"]="1.4.0"; d["plugins"][0]["version"]="1.4.0"; p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
p=pathlib.Path("cpl/__init__.py"); t=p.read_text(encoding="utf-8"); p.write_text(re.sub(r'__version__ = "[^"]+"','__version__ = "1.4.0"',t),encoding="utf-8")
print("bumped to 1.4.0")
PY
```
Then verify no mojibake / valid JSON:
`python3 -c "import json;[json.load(open(f,encoding='utf-8')) for f in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json']];print('ok')"`

- [ ] **Step 5: Final verification**

Run: `python3 -m unittest discover -s tests` ; `python3 eval/run_eval.py` ; `python3 -m compileall -q cpl hooks eval tests`
Expected: all OK; FPR 0.0%; compile exit 0.

- [ ] **Step 6: Commit**

```bash
git add commands/cpl.md README.md CHANGELOG.md .claude-plugin/ cpl/__init__.py
git commit -m "docs: data masking docs + config; release v1.4.0"
```

---

## Task 5: Open PR

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feat/data-masking
gh pr create -R architonixlabs/claude-prompt-lint --base main --head feat/data-masking \
  --title "Data masking — secret block / PII warn (v1.4.0)" \
  --body "Implements docs/superpowers/specs/2026-06-21-data-masking-design.md. Auto-detects secrets (block, with paste-ready masked prompt) and PII (warn) on every prompt via a new mask skill that runs before the gate. /cpl mask helper, custom patterns, allowlist, log redaction. Fail-open; gate untouched. Tests + eval green."
```

- [ ] **Step 2: Confirm CI**

Run: `gh pr checks <PR#> -R architonixlabs/claude-prompt-lint`
Expected: both `tests + eval` jobs pass.

---

## Self-Review (completed by plan author)

- **Spec coverage:** detection library + Finding/scan/mask_text (Task 1) · detection catalog incl. Luhn (Task 1) · feedback renderers (Task 2) · mask skill hook block/warn + command, registry-before-gate, config block, bypass semantics, disabled/downgrade (Task 3) · log redaction (Task 3 `_log` + test) · custom patterns + allowlist (Task 1) · fail-open (Task 1 `scan` + Task 3) · docs/config/release (Task 4). All spec sections map to a task.
- **Placeholders:** none — every code/test step has complete code.
- **Type consistency:** `Finding(kind,label,category,severity,start,end,preview)`, `scan(text,cfg)->list`, `mask_text(text,findings)->str`, `has_block/has_warn`, `feedback.format_mask_block(findings,masked_prompt)`, `format_mask_warn(findings)`, `Skill(name,run,hook,command)` — used identically across tasks and tests.
- **Note:** the dispatcher already supports a skill registered for both a hook and a command (the registry adds it to both maps); `mask` is the first to use both. `run(ctx)` branches on `ctx.event` to disambiguate.
