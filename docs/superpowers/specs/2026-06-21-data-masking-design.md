# Design: Data masking (secret/PII detection) for cpl

**Date:** 2026-06-21
**Status:** Approved (design), pending implementation plan
**Owner:** Ram Chandra Samal · Architonix Labs

## Summary

Add automatic **secret/PII detection** to cpl. On every prompt (via the existing
`UserPromptSubmit` hook), a new `mask` skill scans for sensitive data: **secrets
block** the prompt before it's sent, **PII warns**. Because the platform cannot
silently rewrite a prompt, a blocked prompt's message includes the **fully-masked
prompt, ready to paste and resend**. A `/cpl mask <text>` command returns a
redacted version on demand.

## Critical platform constraint

Verified against current Claude Code docs (2026-06-21): **no plugin hook can
rewrite or replace the submitted prompt.** `UserPromptSubmit` can only *block*
(exit 2 / `decision:block`) or *append context* (`additionalContext`);
`UserPromptExpansion` can only block. There is **no silent redact-and-send**.

Therefore "masking" = **detect-and-prevent**: block the prompt so the secret
never leaves the machine, and hand the user a ready-to-paste masked version. We
do **not** append "pretend this is redacted" context, because the original
secret would still be sent — that would be false protection.

## Goals

- Auto-detect, on every prompt with no explicit invocation, four families:
  cloud/API secrets, crypto/auth material, connection strings (→ **block**), and
  PII (email/phone/IP/credit-card/SSN → **warn**).
- Block message includes which detectors fired (masked previews) **and the whole
  prompt masked, ready to resend**.
- `/cpl mask <text>` returns a redacted version on demand.
- User-extensible: custom regex patterns and an allowlist in `~/.cpl/config.json`.
- The local log/debug output never stores a matched secret value — only its kind.

## Non-goals (YAGNI)

- No generic high-entropy detector in v1 (too many false positives; a gate that
  cries wolf gets disabled). Custom patterns cover company-specific formats.
- No silent auto-resend of the cleaned prompt (platform can't).
- No network validation of keys.
- No PreToolUse redaction of tool inputs (possible future feature; out of scope).

## Architecture

### Components

1. **`cpl/shared/secrets.py`** (new) — the detection library, stdlib only.
   - `Finding` dataclass: `kind` (e.g. `aws_access_key`), `label` (human),
     `category` (`"secret"|"pii"`), `severity` (`"block"|"warn"`), `start`,
     `end`, `preview` (masked form of the match).
   - Built-in `_PATTERNS`: list of `(kind, label, regex, category, severity)`.
   - `scan(text, cfg) -> list[Finding]` — runs built-in + custom patterns, drops
     allowlisted matches, dedupes overlaps, returns findings sorted by `start`.
     Fully fail-safe: any exception yields `[]` (fail-open — never block on a
     scanner bug).
   - `mask_text(text, findings) -> str` — replaces each finding's span with its
     masked preview (right-to-left to preserve indices).
   - `_preview(kind, value) -> str` — head/tail hint, e.g. `sk-…aB3d`,
     `AKIA…7Q2X`, `j…@e….com`, `«PRIVATE KEY redacted»`.
   - Custom patterns from `cfg["mask"]["custom_patterns"]`
     (`[{name, regex, severity}]`); allowlist from `cfg["mask"]["allowlist"]`
     (exact strings or regexes to ignore). A bad custom regex is skipped, never
     raised.

2. **`cpl/skills/mask.py`** (new) — one `SKILL` with **both**
   `hook="UserPromptSubmit"` and `command="mask"`; `run(ctx)` branches on
   `ctx.event`.
   - Hook path: scan the prompt. If any `block`-severity finding and
     `block_secrets` is on → **block** (payload = the mask-block feedback). Else
     if any `warn`-severity finding and `warn_pii` is on → **inject** a warn
     note. Else → **pass**. Logs only detector kinds.
   - Command path (`/cpl mask <text>`): return `mask_text(text, scan(text))`.

3. **`cpl/registry.py`** (modify) — insert `"mask"` **before** `"gate"` in
   `_SKILL_MODULES`, so secrets are caught first. The dispatcher already runs all
   hook skills in order, returns on the first `block`, and accumulates `inject`
   notes — so **no dispatcher change** is needed.

4. **`cpl/shared/feedback.py`** (modify) — `format_mask_block(findings,
   masked_prompt, bypass)` and `format_mask_warn(findings)` renderers.

### Data flow

```
prompt submitted
   │
   ▼  UserPromptSubmit hook → dispatcher runs hook skills in order:
   │
   ├─ mask skill (runs FIRST)
   │     scan(prompt)
   │     ├─ secret found + block_secrets → BLOCK (reason: kinds + masked prompt)   ── stop
   │     ├─ only PII + warn_pii         → inject a "[cpl] PII note" + continue
   │     └─ nothing                     → pass
   │
   └─ gate skill (runs only if mask didn't block) → its usual quality verdict
```

## Detection catalog (v1)

**Secrets → block**

| kind | pattern (informal) |
|------|--------------------|
| `aws_access_key` | `A(KIA|SIA)[0-9A-Z]{16}` |
| `google_api_key` | `AIza[0-9A-Za-z_\-]{35}` |
| `openai_key` | `sk-(proj-)?[A-Za-z0-9]{20,}` |
| `anthropic_key` | `sk-ant-[A-Za-z0-9\-_]{20,}` |
| `github_token` | `gh[pousr]_[A-Za-z0-9]{36,}` |
| `slack_token` | `xox[baprs]-[A-Za-z0-9-]{10,}` |
| `stripe_key` | `(sk|rk)_live_[A-Za-z0-9]{16,}` |
| `private_key` | `-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----` |
| `jwt` | `eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}` |
| `bearer_token` | `(?i)bearer\s+[A-Za-z0-9._\-]{20,}` |
| `secret_assignment` | `(?i)\b(api[_-]?key|secret|token|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*['"]?[A-Za-z0-9\-_./+]{8,}` |
| `password_assignment` | `(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['"]?[^\s'"]{6,}` |
| `connection_string` | `(?i)\b(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqps?)://[^:\s/]+:[^@\s/]+@` |

**PII → warn**

| kind | pattern (informal) |
|------|--------------------|
| `email` | standard email |
| `ipv4` | dotted-quad with range validation |
| `phone` | optional `+1`, area code, 7 digits |
| `credit_card` | 13–19 digits w/ separators, **Luhn-validated** to cut false positives |
| `ssn` | `\b\d{3}-\d{2}-\d{4}\b` |

Patterns are tuned for **low false positives** (the block path is disruptive).
Where a pattern is broad (credit card), a validator (Luhn) gates it.

## Behavior details

- **Scan everything** non-empty. No `min_length_skip` (a 20-char prompt can be a
  bare key). The mask skill does not inherit the gate's Tier-0 escapes.
- **Bypass:** `!!` does **not** skip a secret block — the **allowlist** is the
  deliberate "I meant to send this" path. `!!` *does* skip PII warns (consistent
  with skipping quality warns). `"mask": false` disables the skill;
  `"block_secrets": false` downgrades secrets to warn-only.
- **Block message** (shown to the user only, never sent to the model):
  ```
  🔒 cpl blocked — your prompt contains data that shouldn't be sent:
    • OpenAI API key            sk-…aB3d
    • Postgres connection string postgres://u…@…
  Send a cleaned version (copy–paste this):
    «the full prompt, with each secret replaced by its masked preview»
  (Allow a specific value via mask.allowlist in ~/.cpl/config.json.)
  ```
- **Fail-open:** a scanner exception → no findings → prompt passes (logged to the
  debug log). Masking must never break a legitimate prompt.

## Configuration

New `mask` block (deep-merged from `~/.cpl/config.json`):
```json
"mask": {
  "enabled": true,
  "block_secrets": true,
  "warn_pii": true,
  "allowlist": [],
  "custom_patterns": []
}
```
Plus `"mask": true` in the `skills` map. `custom_patterns` entries are
`{"name": "...", "regex": "...", "severity": "block"|"warn"}`.

Masking is governed **only** by `mask.enabled` and the `skills.mask` toggle — it
is **independent of the gate's `enabled`/`mode`**. Turning the gate off, or using
`warn` mode, does not weaken secret blocking; a user who wants no secret
protection sets `mask.enabled` (or `block_secrets`) to `false` explicitly.

## Logging / safety

- The mask skill logs `{event:"mask", action, kinds:[...]}` — **kinds only,
  never the matched value**. The existing prompt log already stores no prompt
  text; this preserves that invariant.
- The dispatcher debug log records `prompt_len` and payload keys, not content —
  unchanged. No code path writes a detected secret to disk.

## Testing

Pure-stdlib `unittest`:
- `tests/test_secrets.py` — each detector matches representative positives;
  negatives (normal prose/code, a UUID, a git SHA, a version number) do **not**
  match; Luhn validation rejects a non-card 16-digit number; allowlist drops a
  match; a custom pattern is honored; a bad custom regex is skipped; `mask_text`
  redacts in place; `_preview` never returns the full secret; `scan` is fail-safe
  on bad input.
- `tests/test_mask.py` — hook path blocks on a secret (action `block`, payload
  contains the masked prompt, **not** the raw secret); PII-only path injects a
  warn; clean prompt passes; `block_secrets:false` downgrades to warn;
  `mask:false`/disabled passes; `/cpl mask` command returns redacted text;
  `!!`-prefixed prompt with a secret is **still blocked**.
- Existing gate eval (FPR 0%) and all current tests stay green; confirm mask runs
  before gate (a secret prompt blocks with a mask reason, not a gate reason).

## Backward compatibility

- New skill, off-path for any prompt without sensitive data → no behavior change
  for existing users.
- No change to the gate, the other skills, or the dispatcher.

## Build order (for the plan)

1. `secrets.py` library + `tests/test_secrets.py` (detectors in isolation).
2. `feedback.py` mask renderers.
3. `mask.py` skill (hook + command) + registry order + config block +
   `tests/test_mask.py`.
4. Docs (README masking section + config table), `commands/cpl.md` row,
   CHANGELOG, version bump.
