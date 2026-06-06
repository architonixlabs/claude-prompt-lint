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
| `/cpl expand <prompt>` | Scaffolds a terse prompt into Task / Anchor / Constraints / Done-when. |
| `/cpl explain <prompt>` | Detailed breakdown of what's weak and why. |
| `/cpl scope <prompt>` | Checks that referenced files/symbols exist in the repo. |
| `/cpl profile` | Your recurring prompt weaknesses over time (local log). |
| `/cpl stats` | Gated/passed counts + estimated tokens saved from your local log. |
| `/cpl template <name>` | Emits a reusable prompt template (`bugfix`, `refactor`, `migration`). |
| `/cpl help` | List available commands. |

All eight skills are enabled by default; toggle any of them under `"skills"` in
`~/.cpl/config.json` (your per-user override; survives plugin updates).

## Behaviour notes

- All evaluation is **local**. No API tokens are spent by cpl itself.
- The output above is the skill's result. If the user asked you to actually
  rewrite their prompt (not just scaffold it), use the `rewrite` output as
  analysis and author a concrete tightened prompt for them — but never send it
  on their behalf; present it for them to copy.
