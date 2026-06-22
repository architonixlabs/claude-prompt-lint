# Scope: PreToolUse secret-in-context guard

> Closes the gap Murat named: today cpl's secret scan only sees the *typed
> prompt*, but the real leak vector in agentic coding is **the agent reading a
> secret-bearing file into context on its own** (`.env`, `*.pem`, `id_rsa`,
> `credentials`) — which `UserPromptSubmit` never sees. A `PreToolUse` hook sits
> exactly where that read happens.

## Why this is the right "make it better" move

cpl's only defensible ground is the **interception point**. Right now it guards
one door (the prompt box). The autonomous-agent era's actual leak path is a
*different* door — the agent's own `Read`/`Bash` of a secret file. Guarding that
door turns the secret-catch from "fires on a rare manual paste" (seatbelt that
rarely deploys) into "fires whenever an agent explores a repo that has secrets"
(seatbelt that actually earns its seat). Same wedge, far higher hit rate.

## Feasibility: GREEN (contract confirmed)

- `PreToolUse` fires before `Read` and `Bash` (and all tools).
- Payload: `tool_name`, `tool_input` — `Read` → `tool_input.file_path`,
  `Bash` → `tool_input.command`.
- Decisions: `permissionDecision` ∈ `deny` (block) | `ask` (force a permission
  dialog) | `allow` | `defer`/omitted (proceed); plus `additionalContext` to
  warn without blocking. Exit code 2 also blocks (stderr → Claude).
- One plugin registers both hooks; `matcher: "Read|Bash"` scopes the guard.
- Reuses `cpl.shared.secrets` verbatim — no new detection logic.

⚠️ **Verify before shipping.** The Claude Code hook output contract has shifted
across versions (the README already warns about this for `UserPromptSubmit`).
Step 1 of implementation is a smoke test of the exact `permissionDecision` JSON
against the installed CC version — do not build blind.

## Design (stateless — dodges the "you built the breach" trap)

A new hook-side skill `guard` with `hook="PreToolUse"`. Flow:

1. **Cheap filename gate first.** Match `file_path` (Read) / paths in `command`
   (Bash) against a sensitive-name heuristic: `.env*`, `*.pem`, `*.key`,
   `id_rsa`, `*credentials*`, `*.p12`, `secrets.*`, etc. If nothing matches and
   it's a Read of an ordinary source file → **proceed immediately** (no content
   scan, no latency on the 99% case).
2. **Transient content scan only on a match.** For a matched file under a size
   cap, read it transiently and run `secrets.scan`. Decide, then **discard** —
   never persist findings, never index *where* secrets live (that index is the
   breach Winston warned about). For Bash, scan the `command` text directly
   (`cat .env`, `echo $AWS_SECRET_ACCESS_KEY`).
3. **Decision policy — `ask` by default, not `deny`.** A hard `deny` that
   misfires gets the plugin uninstalled (low-false-positive bias is sacred).
   `ask` interrupts the agent's autonomous read and puts a human in the loop —
   the seatbelt, not a wall. Configurable per the `guard` config block:
   `mode: ask | deny | warn | off`.
4. **Fail-open is sacred.** Any error — unreadable file, malformed payload,
   regex bug, unknown CC contract — defers to "allow." A guard bug must never
   freeze the agent. Same rule as the gate.
5. **Metadata-only logging.** Log `kind` + `tool` + action, like the gate.
   Never the secret value, never the file path (a path can itself leak intent).

## Plumbing

- `hooks/hooks.json`: add a `PreToolUse` entry (matcher `Read|Bash`) calling
  `dispatcher.py --event PreToolUse`.
- `dispatcher.py`: new emit path for PreToolUse — translate a `Result` into the
  `permissionDecision` JSON (the existing block/inject emitters are for
  UserPromptSubmit and don't apply).
- `cpl/skills/guard.py`: `SKILL = Skill(name="guard", run=run,
  hook="PreToolUse")`; registry already routes arbitrary hook events.
- `config`: `guard` block (`mode`, `sensitive_globs`, `max_scan_bytes`,
  reuse `mask.allowlist`/`custom_patterns` so detection stays consistent).
- Default **off or `warn`** for the first release — earn trust before `ask`.

## What this honestly does NOT do (state it, don't overclaim)

- Not non-bypassable, not enterprise DLP. A compiled program or an un-hooked
  path can still read the env; this guards the *agent's* `Read`/`Bash`, not the OS.
- False-negative risk on novel secret formats remains (regex-bound).
- It catches the **common, high-value** case — an agent autonomously reading
  `.env`/keys — which is the specific vector that made the prompt-only scan
  "rarely fire." That's the win; the rest is for network DLP, not us.

## Phased plan

1. **Verify** the PreToolUse JSON contract on the installed CC version (smoke test).
2. **Build** `guard.py` + dispatcher emit path + hooks.json entry, default `warn`.
3. **Test** (stdlib unittest): sensitive-name match, transient scan decision,
   fail-open on bad payload, metadata-only log, `mode` switch.
4. **Dogfood** at `warn`, watch the (new) guard counter in `/cpl stats`, then
   graduate the default to `ask` once the false-positive rate is trusted.
