# Design: Prompt frameworks in `/cpl expand`

**Date:** 2026-06-13
**Status:** Approved (design), pending implementation plan
**Owner:** Ram Chandra Samal · Architonix Labs

## Summary

Add a library of selectable **prompt frameworks** (AIM, RACE, COSTAR, TAG, plus
the existing default) to the `expand` skill, and make `/cpl expand` **interactive
and personalizable**: pick a framework, get walked through its sections, honor
saved defaults, and define your own frameworks. Frameworks are declarative JSON
files — adding one is dropping a file, no code.

## Goals

- A data-driven framework library: one JSON file per framework, loaded from the
  plugin **and** from `~/.cpl/frameworks/` (user override/extension).
- `/cpl expand [framework] [prompt]` applies a framework to the user's prompt.
- **Interactive** flow (Claude-driven): a framework **picker** when none is named,
  and a **guided section fill** that assembles the final prompt.
- **Personal defaults** in config: preferred framework, tone, verbosity, and an
  interactive on/off toggle.
- **Custom frameworks**: users add/override frameworks in `~/.cpl/frameworks/`.
- Fully backward compatible: `/cpl expand fix the login bug` still works.

## Non-goals (YAGNI)

- No per-framework model parameters or fine-tuning.
- No GUI/browser UI — interactivity uses Claude's existing question/conversation
  ability in the command flow.
- No analytics on framework usage.
- No framework authoring wizard (a user writes a small JSON file by hand or
  copies a shipped one).

## Key architectural constraint

The gate runs as a **headless `UserPromptSubmit` hook** — it cannot hold a
conversation. So interactivity **cannot** live in Python. The split is:

- **Python (`expand` skill + `frameworks.py`)** — the framework *library and
  data*: load, merge, resolve, and render a one-shot result or emit a machine-
  readable *framework spec* for Claude to drive.
- **Claude (via `commands/cpl.md` instructions)** — the *conversation*: picker
  and guided fill, then assembling the final prompt.

This mirrors how `rewrite` already has Claude author the final tightened prompt,
and it keeps the **gate 100% local / zero-token**. Only the opt-in `/cpl expand`
command uses the user's Claude session. (Local-first applies to *evaluation* —
the gate — not to opt-in assist commands; a fully-local one-shot path remains
via the local model.)

## Components

### 1. Framework library — `cpl/shared/frameworks.py` (new)

Loads `*.json` from two roots and merges them (user wins on name/alias
collision):

1. Shipped: `<plugin>/frameworks/` (resolved via `${CLAUDE_PLUGIN_ROOT}`,
   falling back to repo root — same pattern as `template.py`).
2. User: `~/.cpl/frameworks/`.

Fail-safe: a missing directory or a malformed JSON file is skipped and never
raises. Public surface:

- `load_frameworks() -> dict[str, Framework]` — keyed by lowercase name; aliases
  also map to the same object.
- `resolve(token, cfg) -> (Framework, bool)` — given the first CLI token and
  config, return `(framework, token_was_consumed)`. If `token` matches a known
  name/alias it is consumed; otherwise the configured `default_framework`
  (fallback `"default"`) is returned and the token is left as prompt text.
- `list_frameworks() -> list[(name, description)]` — for the picker / no-arg list.

A `Framework` is a small dataclass: `name`, `aliases`, `description`,
`sections` (ordered list of `{label, guidance}`).

### 2. Framework data format — `frameworks/*.json` (new)

```json
{
  "name": "RACE",
  "aliases": ["race"],
  "description": "Role, Action, Context, Expectation — a general task framework.",
  "sections": [
    {"label": "Role",        "guidance": "Who the assistant should act as"},
    {"label": "Action",      "guidance": "The specific task to perform"},
    {"label": "Context",     "guidance": "Background, constraints, relevant files"},
    {"label": "Expectation", "guidance": "What a good result looks like"}
  ]
}
```

Stdlib-parseable (JSON, not YAML) to honor the zero-dependency rule.

**Seed library (5 shipped):**

- `default` — Task / Anchor / Constraints / Done-when (today's expand structure,
  so the no-framework path is byte-for-byte unchanged).
- `aim` — Audience / Intent / Message.
- `race` — Role / Action / Context / Expectation.
- `costar` — Context / Objective / Style / Tone / Audience / Response.
- `tag` — Task / Action / Goal.

### 3. Personal defaults — config

New `expand` block in `config/cpl.config.json` (deep-merged from
`~/.cpl/config.json`):

```json
"expand": {
  "default_framework": "default",
  "interactive": true,
  "tone": "neutral",
  "verbosity": "concise"
}
```

- `default_framework` — used when no framework token is given.
- `interactive` — whether `/cpl expand` defaults to guided mode vs one-shot.
- `tone` / `verbosity` — style hints fed into both the guided fill and the
  model-applied one-shot.

All keys optional and individually defaulted (`cfg.get(...)`), per the config
deep-merge rule.

### 4. `expand` skill — modes (`cpl/skills/expand.py`, modified)

Argument parsing: split the first whitespace token off `ctx.args`. Use
`frameworks.resolve(first_token, cfg)`; if consumed, the remainder is the prompt,
else the whole `args` is the prompt with the default framework.

- **No args** → emit usage + the framework list (`list_frameworks()`).
- **Interactive (default when `expand.interactive` is true)** → emit a
  `FRAMEWORK SPEC` block: framework name + description, ordered sections
  (label + guidance), the user's raw prompt (may be empty), the active
  tone/verbosity, and the full framework list. `commands/cpl.md` consumes this.
- **One-shot (`--quick` flag, or `interactive:false`)** → today's behavior:
  - model on → `model_client.generate(...)` with a system prompt **generated from
    the framework's sections** (replacing the hard-coded TAC-D system prompt).
  - model off → a static scaffold built from the framework's sections.

The `--quick` flag is detected as the first token (before framework resolution)
and stripped.

### 5. Interactive flow — `commands/cpl.md` (modified)

For `/cpl expand`, instruct Claude to:

1. Run the dispatcher to obtain the framework spec + list.
2. **Picker:** if no framework was named and `interactive` is on, ask the user to
   choose from the list (AskUserQuestion).
3. **Guided fill:** for each section of the chosen framework, gather content
   conversationally — seed anything already present in the user's prompt, ask
   only for what's missing, and respect `tone`/`verbosity`. (Sections beyond
   AskUserQuestion's 4-option limit, e.g. COSTAR's six, are gathered
   conversationally rather than via a single tool call.)
4. **Assemble:** present the final structured prompt for the user to copy. Never
   auto-send it.
5. **Escape:** `/cpl expand --quick …` relays the Python one-shot output verbatim
   with no conversation.

## Data flow

```
/cpl expand race fix the login bug
   │
   ├─ commands/cpl.md → dispatcher: expand "race fix the login bug"
   │     └─ frameworks.resolve("race") → RACE consumed; prompt="fix the login bug"
   │     └─ emits FRAMEWORK SPEC (RACE sections + prompt + tone/verbosity)
   │
   ├─ interactive? ── yes ─▶ Claude: (picker skipped, framework named)
   │                          guided fill of Role/Action/Context/Expectation
   │                          → assembled prompt to copy
   │              └─ no (--quick) ─▶ Python one-shot (model or static scaffold)
```

## Error handling / fail-safe

- Framework dir(s) missing or a file malformed → skipped; the loader still
  returns whatever parsed, and always includes a hard-coded `default` fallback so
  `expand` never breaks.
- Unknown explicit framework token that *looks* like a framework but isn't found
  → treated as prompt text under the default framework (no error).
- Config absent/partial → every `expand.*` key individually defaulted.

## Testing

Pure-stdlib `unittest`, added to `tests/`:

- Framework loading: shipped files parse; alias resolution; `~/.cpl/frameworks/`
  override wins; malformed file skipped without raising.
- `resolve()`: framework token consumed vs left as prompt; default fallback;
  config `default_framework` honored.
- `expand` parsing: `--quick` stripping; framework-vs-prompt split;
  backward-compat (`expand fix login` with `interactive:false` == today's output).
- No-arg listing includes all five seed frameworks.
- Existing gate eval (FPR 0%) and all current tests remain green.

## Backward compatibility

- `/cpl expand fix the login bug` with `interactive:false` (or `--quick`) yields
  the same scaffold/model output as v1.2.0.
- The `default` framework reproduces Task/Anchor/Constraints/Done-when exactly.
- No change to the gate, the hook, or any other skill.

## Build order (for the implementation plan)

1. `frameworks.py` + the 5 shipped JSON files + tests (library in isolation).
2. `expand.py` rewired onto the library; `--quick` + config; one-shot paths; tests.
3. `commands/cpl.md` interactive instructions (picker + guided fill).
4. Docs (README frameworks section + config table), CHANGELOG, version bump.
