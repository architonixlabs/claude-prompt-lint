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

> **Requirements:** Python 3.8+ on your `PATH`. No pip packages — the plugin
> uses only the Python standard library.

### 1. Get the code

```bash
git clone https://github.com/architonixlabs/claude-prompt-lint
cd claude-prompt-lint
./install.sh           # macOS / Linux  — verifies Python + self-checks
# or on Windows:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### 2. Register it as a Claude Code plugin

Add this repo as a plugin (via your plugin marketplace config, or a local
plugin path). Claude Code discovers `commands/` and `hooks/hooks.json`
automatically, and sets `${CLAUDE_PLUGIN_ROOT}` so the hook can find the
dispatcher.

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
| `/cpl rewrite <prompt>` | Returns a tightened skeleton of your prompt to copy. |
| `/cpl explain <prompt>` | Detailed breakdown of what's weak and why. |
| `/cpl stats` | Gated/passed counts + estimated tokens saved (from your local log). |
| `/cpl help` | List available commands. |

---

## Configuration

Edit [`config/cpl.config.json`](config/cpl.config.json). You can also drop a
`~/.cpl/config.json` to override per-user, or point `$CPL_CONFIG` at a file.

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
  "skills": { "gate": true, "rewrite": true, "stats": true, "explain": true }
}
```

| Key | Meaning |
|-----|---------|
| `mode` | `warn` (inject a note, let it proceed) or `block` (erase + show feedback). |
| `bypass_prefix` | Prefix that skips the gate entirely. Default `!!`. |
| `min_length_skip` | Prompts shorter than this many chars are never gated. |
| `use_model` | Turn on the Tier 2 local model (needs Ollama — see below). |
| `fail_open` | **Sacred.** Model down ⇒ prompt passes. Keep this `true`. |
| `log_path` | Local JSONL prompt log. `~` and env vars are expanded. |
| `skills` | Enable/disable individual skills. |

**Default mode is `warn`** — lenient on purpose. Flip to `block` once you trust
the gate.

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
cpl/skills/             gate, rewrite, stats, explain, … (4 stubs for v1.x)
cpl/shared/             rules, model_client, log, feedback, config
config/cpl.config.json  configuration
eval/                   labelled prompt sets + run_eval.py
templates/              prompt templates (bugfix / refactor / migration)
```

### Roadmap

- **v1.0 (now):** gate, rewrite, stats, explain. Rules + optional local model.
- **v1.x:** `profile` (your recurring weaknesses), `expand` (scaffold terse
  prompts), `scope` (verify referenced files/symbols exist), `template`.

---

## Notes & limitations

- **Windows:** paths are handled cross-platform; the hook forces UTF-8 stdout
  so feedback renders on `cp1252` consoles. PowerShell installer included.
- **Privacy:** the prompt log is local JSONL under `~/.cpl/`. It never leaves
  your machine and is `.gitignore`d.
- **Not** an auto-rewriter that silently sends your prompt, a code/security
  scanner, or a cloud-API evaluator. Scope is *prompt quality, before send*.

## License

MIT © 2026 Ram Chandra Samal · Architonix Labs LLP. See [LICENSE](LICENSE).
