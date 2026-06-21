---
description: Lint your prompt before you spend the token — run a cpl skill (rewrite, stats, explain, …).
argument-hint: <skill> [args]   e.g. rewrite fix the login bug
allowed-tools: Bash(python3:*), Bash(python:*)
---

# /cpl — claude-prompt-lint

Route to a cpl skill. The first word of `$ARGUMENTS` is the skill name; the
rest is passed to it as arguments.

Run the dispatcher in command mode and relay its output to the user verbatim:

```
!python3 "${CLAUDE_PLUGIN_ROOT}/hooks/dispatcher.py" --command $ARGUMENTS
```

## Available skills

| Command | What it does |
|---------|--------------|
| `/cpl rewrite <prompt>` | Returns a tightened version of your prompt to copy. |
| `/cpl expand [framework] <prompt>` | Restructure a prompt with a framework (default/aim/race/costar/tag, or your own). Interactive unless `--quick`. |
| `/cpl explain <prompt>` | Detailed breakdown of what's weak and why. |
| `/cpl scope <prompt>` | Checks that referenced files/symbols exist in the repo. |
| `/cpl profile` | Your recurring prompt weaknesses over time (local log). |
| `/cpl stats` | Gated/passed counts + estimated tokens saved from your local log. |
| `/cpl template <name>` | Emits a reusable prompt template (`bugfix`, `refactor`, `migration`). |
| `/cpl mask <text>` | Returns a redacted copy of text (secrets/PII masked) to paste back. |
| `/cpl init [--quick]` | Generate/refresh a project-context section in `CLAUDE.md` (then I enrich it, unless `--quick`). |
| `/cpl help` | List available commands. |

All eight skills are enabled by default; toggle any of them under `"skills"` in
`~/.cpl/config.json` (your per-user override; survives plugin updates).

## Behaviour notes

- All evaluation is **local**. No API tokens are spent by cpl itself.
- **Data masking is automatic.** Every prompt is scanned locally; a detected
  secret (API key, private key, connection string…) blocks the prompt before it
  is sent, and the block message includes the prompt already masked to resend.
  PII (emails, etc.) only warns. This runs even if the gate is off.
- The output above is the skill's result. If the user asked you to actually
  rewrite their prompt (not just scaffold it), use the `rewrite` output as
  analysis and author a concrete tightened prompt for them — but never send it
  on their behalf; present it for them to copy.

### `/cpl expand` (interactive)

The dispatcher output for `expand` may be a `CPL_EXPAND_SPEC` block (lines:
`framework:`, `framework_named:` (true/false), `description:`, `tone:`,
`verbosity:`, `prompt:`, a `sections:` list of `- Label: guidance`, and an
`available_frameworks:` list). When you see it, DO NOT relay it verbatim — drive
an interactive flow instead:

1. **Picker.** If `framework_named:` is `false`, offer the
   `available_frameworks` list and let the user choose. If it's `true`, they
   already named one — skip the picker.
2. **Guided fill.** For each section in `sections:`, gather content with the
   user. Seed each section from anything already in `prompt:`; only ask about
   sections that aren't already covered. Respect `tone:` and `verbosity:`.
3. **Assemble.** Present the finished prompt as labelled lines for the user to
   copy. Never send it on their behalf.

If the user wants no conversation, tell them to use `/cpl expand --quick
[framework] <prompt>`, which the dispatcher renders directly (relay that
verbatim). Output that is NOT a `CPL_EXPAND_SPEC` block (a scaffold, a model
result, or the framework list) is already final — relay it verbatim.

**Reserved tokens:** `default`, `aim`, `race`, `costar`, `tag` (and any custom
framework name) are treated as the framework when they're the **first** word of
the args. So `/cpl expand race the login bug` means framework=`race`,
prompt=`the login bug`. If a prompt genuinely needs to start with one of those
words, lead with an explicit framework, e.g. `/cpl expand default race
condition in worker.py`.

### `/cpl init`

The dispatcher writes a deterministic factual baseline into a cpl-managed
section of `CLAUDE.md` and prints a summary. If that output contains an `ENRICH:`
line (i.e. the user did not pass `--quick`), read the repo and rewrite ONLY the
text between the `<!-- cpl:context:start -->` and `<!-- cpl:context:end -->`
markers to add a short architecture / conventions / gotchas note — concise,
since `CLAUDE.md` loads every session. Never touch anything outside the markers.
