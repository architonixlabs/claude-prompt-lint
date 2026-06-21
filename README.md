# claude-prompt-lint (`/cpl`)

> **Lint your prompt before you spend the token.**

A local-first prompt-quality toolkit for [Claude Code](https://claude.com/claude-code).
It intercepts your prompt the moment you hit enter, evaluates it **on your own
machine**, and flags weak prompts with actionable feedback — *before* any API
tokens are spent on a clarification round-trip.

Built by **Ram Chandra Samal** · Architonix Labs LLP.

---

## Why

Vague, under-specified prompts cost you twice: the model asks a clarifying
question, then you re-send. That round-trip is paid in tokens *after* you hit
enter — too late. `cpl` moves the check **before** send, and runs it locally so
the checker itself costs **zero API tokens**.

```
"fix it"  →  ⚠️  cpl: no concrete anchor — name the file/function/error.
```

## How it works

A `UserPromptSubmit` hook routes your prompt through a tiered, local pipeline:

| Tier | What runs | Cost |
|------|-----------|------|
| **0** | Escape hatches: `!!` bypass, slash commands, very short prompts | instant |
| **1** | Heuristic rules (dangling pronouns, no anchor, no acceptance criteria) | instant, no model |
| **2** | *Optional* local model via [Ollama](https://ollama.com) for genuine ambiguity | sub-second, local |

Most prompts resolve at Tier 0/1 with near-zero latency. The local model only
runs for the genuinely ambiguous middle.

### Design principles (non-negotiable)

1. **Local-first** — no cloud call to evaluate a prompt.
2. **Fail-open** — if the model is down or slow, your prompt passes. A broken
   gate must never block your work.
3. **Low false-positive bias** — lenient by default. A gate that over-blocks
   gets disabled in a day.
4. **Extensible** — a skill registry, not a monolith. The gate is skill #1.

---

## Install

> **Requirements:** Python 3 available as `python3` on your `PATH` (the hook
> invokes `python3`; modern Windows, macOS, and Linux all provide it). No pip
> packages — the plugin uses only the standard library. Developed and verified
> on CPython 3.14; it uses only 3.7-era features, but 3.7–3.13 are untested.

### 1. Get the code

```bash
git clone https://github.com/architonixlabs/claude-prompt-lint
cd claude-prompt-lint
./install.sh           # macOS / Linux  — verifies Python + self-checks
# or on Windows:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### 2. Register it as a Claude Code plugin

This repo ships a marketplace manifest, so the quickest path is:

```
/plugin marketplace add architonixlabs/claude-prompt-lint
/plugin install claude-prompt-lint@architonix-labs
```

Or add it as a local plugin path. Either way, Claude Code discovers
`commands/` and `hooks/hooks.json` automatically and sets
`${CLAUDE_PLUGIN_ROOT}` so the hook can find the dispatcher.

> ⚠️ **Version pin.** Claude Code's `UserPromptSubmit` hook output contract has
> shifted across versions. This plugin is verified against the behavior
> documented below (mid-2026). After a Claude Code upgrade, re-run the smoke
> test (`./install.sh`) and confirm a weak prompt is still flagged.

### 3. Verify

Submit a deliberately vague prompt, e.g.
*"can you just go ahead and make this whole thing better for me"*. In the
default **warn** mode you'll see a quality note; the prompt still proceeds.

---

## Usage

### The gate (automatic)

Just type. Weak prompts get flagged. To bypass on purpose, prefix with `!!`:

```
!! quick throwaway thing, skip the gate
```

### `/cpl` commands

| Command | What it does |
|---------|--------------|
| `/cpl rewrite <prompt>` | Returns a tightened version of your prompt to copy. |
| `/cpl expand [framework] <prompt>` | Restructure a prompt with a framework (interactive). |
| `/cpl explain <prompt>` | Detailed breakdown of what's weak and why. |
| `/cpl scope <prompt>` | Checks that referenced files/symbols actually exist in the repo. |
| `/cpl profile` | Your recurring prompt weaknesses over time (from your local log). |
| `/cpl stats` | Gated/passed counts + estimated tokens saved (from your local log). |
| `/cpl template <name>` | Emits a reusable prompt template (`bugfix`, `refactor`, `migration`). |
| `/cpl help` | List available commands. |

### Prompt frameworks (`/cpl expand`)

`expand` structures a prompt using a named framework. Ships with `default`
(Task/Anchor/Constraints/Done-when), `aim` (Audience/Intent/Message), `race`,
`costar`, and `tag`. `/cpl expand` (no args) lists them.

- Apply one: `/cpl expand race fix the login bug`.
- Interactive by default — cpl walks you through each section. One-shot:
  `/cpl expand --quick race fix the login bug`.
- Personal defaults live under `"expand"` in `~/.cpl/config.json`
  (`default_framework`, `interactive`, `tone`, `verbosity`).
- **Your own frameworks:** drop a JSON file in `~/.cpl/frameworks/` — same shape
  as the shipped ones (`name`, `aliases`, `description`, `sections`). A file that
  reuses a shipped name overrides it.

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

---

## Configuration

**If you installed via the marketplace, configure here:** create
`~/.cpl/config.json` and put only the keys you want to change in it. They're
deep-merged over the defaults, so a one-line file is enough:

```json
{ "mode": "block", "use_model": true }
```

> Why not edit the bundled `config/cpl.config.json`? On a marketplace install
> that file lives inside the version-pinned plugin cache
> (`~/.claude/plugins/cache/architonix-labs/claude-prompt-lint/<version>/`),
> which is overwritten on every update. `~/.cpl/config.json` is yours and
> survives upgrades. (You can also point `$CPL_CONFIG` at any file.)

Resolution order (later wins): built-in defaults → the plugin's bundled
`config/cpl.config.json` → `~/.cpl/config.json` → `$CPL_CONFIG`.

```json
{
  "enabled": true,
  "mode": "warn",
  "bypass_prefix": "!!",
  "min_length_skip": 40,
  "block_threshold": 50,
  "use_model": false,
  "model": "qwen2.5:3b-instruct",
  "model_endpoint": "http://localhost:11434/api/generate",
  "model_timeout_ms": 1500,
  "fail_open": true,
  "log_path": "~/.cpl/prompts.log.jsonl",
  "debug_log": false,
  "skills": {
    "gate": true, "rewrite": true, "stats": true, "explain": true,
    "profile": true, "expand": true, "scope": true, "template": true
  }
}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | Master switch. Set `false` to turn cpl off entirely without uninstalling. |
| `mode` | `warn` | `warn` (inject a note, let it proceed) or `block` (erase + show feedback). |
| `bypass_prefix` | `!!` | Prefix that skips the gate for a single prompt. |
| `min_length_skip` | `40` | Prompts shorter than this many chars are never gated. |
| `block_threshold` | `50` | Tier 2 score (0–100) at or above which the model's verdict flags a prompt. |
| `use_model` | `false` | Turn on the Tier 2 local model (needs Ollama — see below). |
| `model` | `qwen2.5:3b-instruct` | Ollama model name for Tier 2. |
| `model_endpoint` | `http://localhost:11434/api/generate` | Ollama generate endpoint. |
| `model_timeout_ms` | `1500` | Hard timeout for the Tier 2 call. Exceeded ⇒ fail-open (passes). |
| `fail_open` | `true` | **Sacred.** Model down/slow ⇒ prompt passes. Keep this `true`. |
| `log_path` | `~/.cpl/prompts.log.jsonl` | Local JSONL prompt log. `~` and env vars are expanded. |
| `debug_log` | `false` | When `true`, writes hook/skill errors to `cpl-debug.log` next to the log for troubleshooting. |
| `skills` | all on | Enable/disable individual skills by name. |
| `expand` | (object) | `default_framework`, `interactive`, `tone`, `verbosity` for `/cpl expand`. |
| `mask` | (object) | `enabled`, `block_secrets`, `warn_pii`, `allowlist`, `custom_patterns` for data masking. |

**Default mode is `warn`** — lenient on purpose. Flip to `block` once you trust
the gate.

### Turning it off

All of these go in `~/.cpl/config.json` (see Configuration above):

- **For one prompt:** prefix it with `!!` (the `bypass_prefix`) — no config needed.
- **The whole gate, temporarily:** set `"mode": "warn"` (default) so it never
  erases prompts — it only adds a note.
- **Everything:** set `"enabled": false`. cpl stops doing anything; `/cpl`
  commands still work.
- **One skill:** set its entry under `"skills"` to `false`.

---

## Tier 2: the local model (optional)

The rules-only gate already catches the worst offenders. For nuanced
ambiguity, enable a small local model.

```bash
# 1. Install Ollama: https://ollama.com
ollama pull qwen2.5:3b-instruct        # ~2 GB, runs fully on GPU
ollama serve                           # if not already running
```

Then set `"use_model": true` in the config. The model is asked for a strict
JSON verdict (`pass`, `score`, `issues`, `suggestions`) with a hard timeout. If
it's slow, down, or returns junk, **the prompt passes** — fail-open is sacred.

A 1–4B instruct model on a modern GPU (e.g. RTX 3060 12 GB) stays sub-second
once warm (~0.5s for `qwen2.5:3b-instruct`). Two latency notes:

- **Closed port** (Ollama not running): the client pre-flights the connection
  and fails open in well under a second instead of waiting out OS retries.
- **Cold start** (Ollama unloaded the model after idle): the first call can
  exceed the timeout, so that one prompt fails open and passes. Subsequent
  prompts are fast. Set Ollama's `OLLAMA_KEEP_ALIVE` if you want it resident.

> Verified locally: `qwen2.5:3b-instruct` ~0.5s warm. An 8B model like
> `llama3.1` works but ran ~25s cold here — too slow for an inline gate. Stick
> to a small model, or raise `model_timeout_ms` and accept the latency.

---

## Quality (eval)

The gate ships tuned against a labelled eval set ([`eval/`](eval/)):

```bash
python eval/run_eval.py
```

| Configuration | False Positive Rate | False Negative Rate |
|---------------|---------------------|---------------------|
| **Tier 1 only** (rules, no model) | **0.0%** (0/30) | 3.3% (1/30) |
| **Tier 1 + Tier 2** (with `qwen2.5:3b-instruct`) | **0.0%** (0/30) | **0.0%** (0/30) |

Rules-only already holds **0% false positives** — a gate that flags good
prompts gets disabled, so this is the number that matters. The one bad prompt
rules-only misses ("review the whole codebase…") is a borderline ask with no
concrete anchor; enabling the Tier 2 model closes that gap and takes the false
negative rate to **0% — with no new false positives**.

The architecture is what keeps FPR at zero: prompts with concrete anchors
*strong-pass at Tier 1* and never reach the model, so the small local model
(which tends to nitpick well-specified prompts) only adjudicates genuinely
ambiguous, anchor-free cases.

Re-run with the model: `python eval/run_eval.py --use-model` (needs Ollama).

---

## Architecture

Everything is a **skill** behind a tiny common interface; a dispatcher routes
hook events and `/cpl` commands to the right one. Adding a skill = a new file in
`cpl/skills/` plus one line in the registry — no dispatcher changes.

```
hooks/dispatcher.py     entry point (hook + command)
cpl/registry.py         skill discovery + routing
cpl/skills/             gate, rewrite, stats, explain, profile, expand, scope, template
cpl/shared/             rules, model_client, log, feedback, config
config/cpl.config.json  configuration
eval/                   labelled prompt sets + run_eval.py
templates/              prompt templates (bugfix / refactor / migration)
```

### Roadmap

- **v1.0:** gate, rewrite, stats, explain. Rules + optional local model.
- **v1.1 (now):** `profile` (recurring weaknesses), `expand` (scaffold terse
  prompts), `scope` (verify referenced files/symbols exist), `template`.

---

## Notes & limitations

- **Windows:** paths are handled cross-platform; the hook forces UTF-8 stdout
  so feedback renders on `cp1252` consoles. PowerShell installer included.
- **Privacy & the log:** the gate appends one record per evaluated prompt to a
  local JSONL file (default `~/.cpl/prompts.log.jsonl`). It stores metadata —
  action, score, tier, prompt length, and stable issue-category tags — **not
  your prompt text**. It never leaves your machine and is `.gitignore`d.
  - **Clear it:** delete the file (`rm ~/.cpl/prompts.log.jsonl`, or on Windows
    `del %USERPROFILE%\.cpl\prompts.log.jsonl`). `stats` and `profile` simply
    start fresh.
  - **Disable logging:** set `log_path` to a throwaway path, or `"stats": false`
    and `"profile": false` if you don't use those skills. (The gate still logs
    for its own counters; deleting the file anytime is the simplest reset.)
  - Uninstalling the plugin does **not** remove `~/.cpl/` — delete it manually
    if you want it gone.
- **Model variance:** with the Tier 2 model on, a small local model is mildly
  non-deterministic on genuinely borderline prompts, so the false-negative rate
  hovers near (not exactly) 0%. Fail-open guarantees this only ever lets a weak
  prompt through, never blocks a good one.
- **Not** an auto-rewriter that silently sends your prompt, a code/security
  scanner, or a cloud-API evaluator. Scope is *prompt quality, before send*.

## License

MIT © 2026 Ram Chandra Samal · Architonix Labs LLP. See [LICENSE](LICENSE).
