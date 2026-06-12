# Changelog

All notable changes to **claude-prompt-lint** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and this
project adheres to [Semantic Versioning](https://semver.org/).

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
