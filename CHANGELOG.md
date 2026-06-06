# Changelog

All notable changes to **claude-prompt-lint** are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and this
project adheres to [Semantic Versioning](https://semver.org/).

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
