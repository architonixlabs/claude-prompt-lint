# Changelog

All notable changes to **claude-prompt-lint** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and this
project adheres to [Semantic Versioning](https://semver.org/).

## [1.6.0] — 2026-06-22

### Changed

- **Repositioned around the privileged interception point.** The README now
  leads with the two jobs every Claude Code repo actually feels — *never leak a
  secret* and *keep your repo legible to Claude* — and frames prompt-quality as
  an **offer, not a scold**. The local prompt-eval engine is unchanged (still
  0% false-positive on the eval set); what changed is how it speaks.
- **Gate (warn mode) now coaches the assistant instead of scolding the user.**
  The injected note briefs Claude on what's thin and tells it to confirm the
  missing piece in *one* question or proceed on a stated assumption — bounded so
  it works *with* an increasingly capable agent rather than nagging. No change to
  the pass/flag decision (eval FPR/FNR unchanged at 0%/0%). New config
  `feedback_style` (`coach` default, or `note` for the classic user-facing
  nudge) makes this a choice, not a forced behavior.
- **`/cpl help` and the manifests** now lead with the repositioned one-liner.
- **Gate (block mode) offers a fix.** The block message now points at
  `/cpl rewrite` to tighten the prompt, alongside the existing `!!` bypass.

### Added

- **`/cpl init` is now refresh-aware (drift detection).** The written section
  embeds a structural fingerprint; re-running `/cpl init` reports whether the
  repo has *drifted* from the recorded context or is still up to date — the
  freshness signal a one-shot generator (native `/init`) doesn't give you. The
  fingerprint excludes language counts so cpl writing its own `CLAUDE.md` can't
  trigger false drift.
- **Shareable stats.** `/cpl stats` now prints a copy-pasteable hygiene line, and
  `/cpl stats share` emits only that line — cpl's first socially shareable
  artifact (all other value stays private to your machine).

## [1.5.0] — 2026-06-21

### Added

- **Project context (`/cpl init`).** Scans the repo (stack, build/test commands,
  layout, git) and writes a concise, cpl-managed section into the project-root
  `CLAUDE.md` — which Claude Code loads natively each session, so the AI has
  project context without re-deriving it and at zero per-turn token cost. cpl
  fills a deterministic baseline, then enriches it; `--quick` writes baseline
  only. Only the text between the cpl markers is touched — your `CLAUDE.md`
  content is preserved.

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

## [1.3.0] — 2026-06-13

### Added

- **Prompt frameworks for `/cpl expand`.** A data-driven library — `default`,
  `aim`, `race`, `costar`, `tag` — applied with `/cpl expand <framework>
  <prompt>`. `/cpl expand` lists them.
- **Interactive expand.** By default cpl runs a framework picker (when none is
  named) and a guided section fill, then assembles the prompt. `--quick` (or
  `"expand": {"interactive": false}`) keeps the one-shot render.
- **Personal defaults + custom frameworks.** An `"expand"` config block
  (`default_framework`, `interactive`, `tone`, `verbosity`) and user-defined
  frameworks in `~/.cpl/frameworks/*.json` (override shipped ones by name).

## [1.2.0] — 2026-06-13

A review pass turned into five tracked issues (#1–#5), all fixed here.

### Fixed
- **`stats` "tokens saved" read ~0 for almost everyone (#1).** Default mode is
  `warn`, where flags log as `inject`, never `block` — and the estimate counted
  only blocks. Now counts warn flags at half weight (175) alongside blocks
  (350), so the headline metric is non-zero in the default configuration.
- **`scope` reported false "found" for symbols (#2).** Symbol verification used
  a raw substring match, so `parseToken()` matched `parseTokenStream`. Now
  matches on word boundaries, and the symbol regex no longer pulls bare
  snake_case prose (`sign_in`, `log_out`) — snake_case counts only as a call.
- **`explain` showed spurious "model unavailable" (#5).** It inherited the
  gate's 1.5s timeout; a cold Ollama model timed out. Now uses a generous
  interactive timeout like `rewrite`/`expand`.

### Added
- **Bounded prompt log (#4).** The gate appends on every prompt; the log now
  trims to the last 5,000 records once it passes a ~2 MB soft cap, and a new
  `log.tail(n)` reads only the end of the file. `stats`/`profile` use it instead
  of parsing the whole history.
- **CI + test suite (#3).** A `tests/` suite (pure-stdlib `unittest`, zero deps)
  covers the command skills, dispatcher routing, gate fail-open, and regression
  guards for #1/#2/#4. A GitHub Actions workflow runs byte-compile + tests +
  eval on Python 3.9 and 3.12, failing the build if the gate's false-positive
  rate is ever non-zero.

## [1.1.2] — 2026-06-06

Install/config usability fixes found by testing a real marketplace install.

### Fixed
- **Typing bare `/cpl` (no subcommand) crashed** with an argparse error instead
  of showing help. The command spec passes an empty `$ARGUMENTS`, which left
  `--command` with no value. `--command` is now optional (`nargs="?"`) and any
  argparse error falls back to help. `/cpl` alone now prints the help screen.

### Documentation
- **Config now points users to `~/.cpl/config.json`** (the per-user override
  that survives plugin updates) instead of the bundled
  `config/cpl.config.json`, which on a marketplace install lives inside the
  version-pinned plugin cache and is overwritten on every upgrade. Documented
  the full resolution order and that only changed keys are needed (deep-merged).
- Off-switch, `/cpl help`, and the command doc all now reference
  `~/.cpl/config.json`.

> Verified on a real marketplace install: the hook fires in live sessions,
> `${CLAUDE_PLUGIN_ROOT}` resolves, `python3` runs, warn/block/pass all behave,
> and a `~/.cpl/config.json` override (e.g. `{"mode":"block"}`) takes effect.

## [1.1.1] — 2026-06-06

Hardening pass from a cross-validation audit (user, AI-agent, and code-review
perspectives). No behavior changes to the gate's verdicts.

### Fixed
- **`scope` could hang on large repos.** It re-walked the whole tree once per
  referenced file (twice, actually) and per symbol, with no file cap on the
  file lookup. Now it walks the tree once into a basename index, batches all
  symbol lookups into a single pass, and respects the scan cap everywhere —
  reporting `?` when a repo is too large to fully scan.
- **Rewrite/expand output could be mangled.** The output cleaner used
  `str.strip("<<<")`, which strips a *set of characters*, so it chewed through
  angle brackets inside the content (e.g. `<auth.py>`). Now removes each marker
  as a whole prefix/suffix.
- **Dispatcher now flushes stdout** on every emit path, so a clean exit can
  never leave a partially-buffered (unparseable) block payload.
- **`model_client` catches `http.client.HTTPException`** explicitly (truncated
  responses from a crashing Ollama) instead of relying on the catch-all.

### Documentation
- Config table now documents every key (`enabled`, `block_threshold`, `model`,
  `model_endpoint`, `model_timeout_ms`, `debug_log`).
- Added an explicit **"Turning it off"** section (bypass / warn / disable / per
  skill) and a **Privacy & the log** section (what's logged — metadata, not
  prompt text — and how to clear it).
- `/cpl help` now shows live status (enabled, mode, model tier), the bypass
  prefix, the off-switch, all commands, and examples.
- Fixed a stale note in the `/cpl` command doc that said the v1.1 skills ship
  disabled (they're enabled by default).

## [1.1.0] — 2026-06-06

Ships the four differentiator skills that were stubbed in 1.0, all enabled by
default.

### Added
- **`/cpl profile`** — reads your local prompt log and surfaces recurring
  weaknesses over time (a bar chart of issue categories + your top weakness and
  how to fix it). Uses stable category tags, never your prompt text.
- **`/cpl expand <prompt>`** — scaffolds a terse prompt into a structured one
  (Task / Anchor / Constraints / Done-when) with `[placeholders]` for what you
  didn't specify. Model-backed when enabled, static scaffold otherwise.
- **`/cpl scope <prompt>`** — extracts referenced file paths and symbols and
  verifies they exist in the repo, catching typos and stale references before
  you send. Pure filesystem; no model, no network.
- **`/cpl template <name>`** — emits a reusable prompt template
  (bugfix / refactor / migration) from `templates/`.

### Changed
- The gate now records stable issue-category tags in the local log (for
  `profile`); no prompt text is stored.
- `model_client` exposes a generic `generate()` used by both `rewrite` and
  `expand`; the output cleaner now also strips trailing instruction-echo lines
  that small models sometimes append.

### Quality
Gate eval is unchanged: Tier 1 only 0.0% FPR / 3.3% FNR; with
`qwen2.5:3b-instruct` 0.0% / 0.0%.

## [1.0.0] — 2026-06-06

First public release. A local-first prompt-quality gate for Claude Code: it
evaluates your prompt on-machine before any API tokens are spent, and flags
weak prompts with actionable feedback.

### Added
- **Gate skill** (`UserPromptSubmit` hook) with tiered evaluation:
  - Tier 0 — escape hatches (`!!` bypass, slash commands, short prompts).
  - Tier 1 — instant heuristic rules (dangling references, missing anchors,
    no acceptance criteria) with broad anchor detection (paths, symbols,
    errors, routes, numeric constraints, known tool/file names).
  - Tier 2 — optional local model via Ollama (default `qwen2.5:3b-instruct`),
    only for genuinely ambiguous prompts; **fail-open** always.
- **`/cpl` commands:**
  - `rewrite` — a tightened version of your prompt (model-backed when enabled,
    structured scaffold otherwise).
  - `explain` — detailed breakdown of what's weak and why.
  - `stats` — gated/passed counts + estimated tokens saved, from a local log.
  - `help` — list available commands.
- **Skill-registry architecture** — a dispatcher routes hook events and
  commands to pluggable skills. Adding a skill is a new file + one registry
  line.
- **Local model client** — stdlib-only Ollama JSON-contract client with a hard
  timeout, a fast TCP pre-flight probe (closed port fails open in <1s instead
  of ~3s on Windows), and a tolerant normalizer for small-model contract drift.
- **Configuration** (`config/cpl.config.json`) — `warn`/`block` modes, bypass
  prefix, thresholds, per-skill enable/disable, with `~/.cpl/config.json` and
  `$CPL_CONFIG` overrides.
- **Packaging** — plugin manifest, marketplace manifest, `UserPromptSubmit`
  hook registration, POSIX + PowerShell installers, portable launchers, prompt
  templates (bugfix / refactor / migration), MIT license, full README.
- **Eval harness** (`eval/run_eval.py`) with 30 good / 30 bad labelled prompts.

### Quality
Measured on the bundled eval set:

| Configuration | False Positive Rate | False Negative Rate |
|---------------|---------------------|---------------------|
| Tier 1 only (rules) | 0.0% | 3.3% |
| Tier 1 + `qwen2.5:3b-instruct` | 0.0% | 0.0% |

False positives are held at zero by design — anchored prompts strong-pass at
Tier 1 and never reach the model, so the model only adjudicates ambiguous,
anchor-free prompts.

### Design principles
Local-first · fail-open · tiered · low-false-positive bias · extensible.

### Not yet shipped (planned for 1.x)
`profile`, `expand`, `scope`, and `template` skills are present as stubs and
disabled by default.

[1.0.0]: https://github.com/architonixlabs/claude-prompt-lint/releases/tag/v1.0.0
