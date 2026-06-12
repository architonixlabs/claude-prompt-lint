---
project_name: 'claude-prompt-lint'
user_name: 'Ram Chandra Samal'
date: '2026-06-06'
sections_completed:
  [
    'technology_stack',
    'language_rules',
    'architecture_rules',
    'configuration_rules',
    'testing_rules',
    'workflow_rules',
    'anti_patterns',
  ]
existing_patterns_found: 'fresh document'
status: 'complete'
rule_count: 9
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Language:** Python 3, standard library ONLY. Zero pip dependencies — this is
  a hard constraint, not a preference. Do not add `requirements.txt` or import
  any third-party package.
- **Interpreter:** invoked as `python3` (hook + command). Verified on CPython
  3.14; code restricted to 3.7-era features (`from __future__ import
  annotations`, `str` methods, `argparse`, `urllib`, `socket`, `http.client`).
- **Distribution:** Claude Code plugin — `.claude-plugin/plugin.json` +
  `.claude-plugin/marketplace.json`, a `UserPromptSubmit` hook, and a `/cpl`
  slash command. No build step.
- **Optional runtime:** Ollama at `localhost:11434` (`qwen2.5:3b-instruct`) for
  the Tier 2 model. Always optional; the plugin is fully functional without it.

## Critical Implementation Rules

### Fail-open is sacred (the #1 rule)

- NO code path reachable from the `UserPromptSubmit` hook may ever block, raise,
  or error a user's prompt because of an internal failure. Missing config, model
  down, log-write failure, a regex bug, a unicode error — all must degrade to
  "prompt passes."
- Every hook-side function is wrapped so its worst case is a silent pass. When
  adding logic to `gate.py`, `dispatcher.py`, `model_client.py`, or `rules.py`,
  preserve this: catch broadly, default to pass.

### Hook output contract (dispatcher.py)

- The hook emits EXACTLY ONE of: block JSON (`{"decision":"block","reason":...}`),
  plain inject text (appended to context, warn mode), or empty stdout (pass).
- Never write a stack trace or partial payload to stdout. Use the `_write()`
  helper, which flushes — a half-buffered block payload is unparseable by Claude
  Code and silently fails the gate.
- stdout/stderr are reconfigured to UTF-8 at startup (Windows consoles default to
  cp1252 and crash on the ⛔/→ glyphs in feedback).
- The hook payload's prompt field may be `prompt` OR `user_prompt` across Claude
  Code versions — read both.

### Extensibility — the skill registry

- Adding a skill = (1) a new module in `cpl/skills/` exposing
  `SKILL = Skill(name=..., run=run, hook=?/command=?)`, and (2) one line in
  `registry._SKILL_MODULES`. Nothing else — no dispatcher changes.
- A skill's `run(ctx: Context) -> Result`. `Result.action` is one of
  `pass | block | message | inject`. Hook skills set `hook="UserPromptSubmit"`;
  command skills set `command="<name>"`.
- Skills are gated by the `skills` config map; a disabled skill is simply not
  registered.

### Configuration

- Resolution is a DEEP MERGE (later wins): built-in `DEFAULTS` →
  bundled `config/cpl.config.json` → `~/.cpl/config.json` → `$CPL_CONFIG`.
- Users configure via `~/.cpl/config.json` (survives plugin updates). NEVER tell
  users to edit the bundled config — on a marketplace install it lives in the
  version-pinned plugin cache and is overwritten on upgrade.
- A user override file is partial; only changed keys are present. Don't assume
  any key exists — always `cfg.get(key, default)`.

### Privacy / logging

- The prompt log (`~/.cpl/prompts.log.jsonl`) stores METADATA ONLY — action,
  score, tier, prompt length, and stable issue-category tags. NEVER log prompt
  text. The `profile`/`stats` skills read these tags, not content.
- Log writes are best-effort and must never raise.

### The tiered gate (gate.py)

- Tier 0 escape hatches (bypass prefix, slash/`!` commands, `< min_length_skip`)
  → Tier 1 heuristic rules → Tier 2 optional model. Anchored prompts strong-pass
  at Tier 1 and must NOT reach the model (small models over-flag specific
  prompts — this is what keeps false positives at 0%).
- Penalty bands (`_STRONG_PASS_MAX`, `_STRONG_FAIL_MIN`) are EVAL-TUNED. If you
  touch `rules.py` or these bands, re-run `python eval/run_eval.py`
  (and `--use-model` if Ollama is up). Target: 0% false-positive rate; never
  regress it.

### Testing

- `eval/` IS the test suite — there is no pytest. `eval/run_eval.py` measures
  false-positive / false-negative rates against `prompts_good.txt` /
  `prompts_bad.txt`. Run it after any change to `rules.py`, `gate.py`, or the
  bands. Keep FPR at 0%.
- For quick checks, run the dispatcher directly:
  `echo '{"prompt":"..."}' | python3 hooks/dispatcher.py --event UserPromptSubmit`
  and `python3 hooks/dispatcher.py --command <skill> <args>`.

### Local model client (model_client.py)

- stdlib `urllib` only. Always: TCP pre-flight `_port_open` probe (so a closed
  Ollama port fails open in <1s instead of ~3s of Windows connect retries), a
  hard timeout, and a tolerant `_normalize` (small models return malformed JSON,
  dict-shaped issues, floats for scores).
- `generate()` is the raw text path (used by `rewrite`/`expand`); `evaluate()`
  is the JSON-verdict path (used by the gate). The output cleaner strips echoed
  delimiters as whole prefixes/suffixes — never `str.strip(charset)`, which eats
  angle brackets inside content.

### Development Workflow Rules

- snake_case modules/functions; module docstrings explain the "why."
- Commits: conventional prefixes (`feat:`/`fix:`/`docs:`), end with a
  `Co-Authored-By:` trailer. Branch off `main`; commit/push only when asked.
- Versioning: semver bumped in THREE files together —
  `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (metadata +
  plugin entry), and `cpl/__init__.py`. Add a `CHANGELOG.md` entry and tag
  `vX.Y.Z`.
- `.gitattributes` enforces LF for `*.sh`, CRLF for `*.ps1`. Don't fight it.
- Paths: use `${CLAUDE_PLUGIN_ROOT}` in manifests; forward slashes / `os.path` /
  `pathlib` in code. Must work on Windows AND Unix.

### Critical Don't-Miss Rules (anti-patterns)

- ❌ Adding any pip dependency. ❌ Letting an exception escape the hook path.
  ❌ Logging prompt text. ❌ Telling users to edit the bundled config.
- ❌ `str.strip("<<<")` to remove a delimiter (it's a char-set, not a substring).
- ❌ Re-walking the repo tree per item in `scope.py` — build one index, honor
  `_MAX_FILES_SCAN`.
- ❌ Editing JSON with `json.dumps` default encoding (it mangled an em-dash into
  mojibake once) — write UTF-8 and verify.
- ❌ Claiming an exact 0% model false-negative rate — a small local model is
  mildly non-deterministic on borderline prompts; fail-open means it only ever
  lets a weak prompt through, never blocks a good one.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code in this project.
- Follow ALL rules exactly. When in doubt, prefer the more restrictive option —
  and for anything touching the hook path, prefer fail-open.
- After changing `rules.py` / `gate.py` / the tier bands, run
  `python eval/run_eval.py` and confirm FPR stays at 0%.

**For Humans:**

- Keep this file lean and focused on what agents miss; delete rules that become
  obvious.
- Update when the stack, the skill interface, the config resolution, or the
  release process changes.

Last Updated: 2026-06-06
