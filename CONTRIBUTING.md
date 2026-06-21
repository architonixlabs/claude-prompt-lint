# Contributing to claude-prompt-lint

Thanks for your interest! `cpl` is a small, local-first Claude Code plugin with
a few firm constraints that keep it fast and trustworthy. Please read these
before opening a PR.

## Ground rules (non-negotiable)

- **Zero dependencies.** The plugin uses the Python **standard library only** —
  no `requirements.txt`, no third-party imports. Tests use stdlib `unittest`.
- **Fail-open is sacred.** Nothing reachable from the `UserPromptSubmit` hook
  may ever block or error a user's prompt because of an internal failure
  (missing config, model down, a regex bug, unicode). Every failure degrades to
  "the prompt passes."
- **Never log prompt text or secret values.** The local log stores metadata and
  stable category/detector tags only.
- **Keep false positives near zero.** A gate or a secret-block that cries wolf
  gets disabled on day one.

## Getting set up

Requires Python 3 on your `PATH` (invoked as `python3`). No install step.

```bash
git clone https://github.com/architonixlabs/claude-prompt-lint
cd claude-prompt-lint
python3 -m unittest discover -s tests      # run the test suite
python3 eval/run_eval.py                    # gate quality eval (FPR must stay 0%)
```

## Before you open a PR

1. **Tests pass:** `python3 -m unittest discover -s tests`.
2. **Eval is clean:** `python3 eval/run_eval.py` shows **False Positive Rate
   0.0%**. CI fails the build otherwise.
3. **Add tests** for new behavior, including a regression guard if you fixed a
   bug.
4. **Update `CHANGELOG.md`** under a new or the unreleased version heading.
5. **Byte-compile clean:** `python3 -m compileall -q cpl hooks eval tests`.

CI runs compile + tests + eval on Python 3.9 and 3.12.

## Architecture in one minute

- `hooks/dispatcher.py` — entry point for the hook and `/cpl` commands.
- `cpl/registry.py` — skill registry + the `Skill`/`Context`/`Result` interface.
- `cpl/skills/` — one file per capability (gate, mask, rewrite, expand, …).
- `cpl/shared/` — `rules`, `secrets`, `model_client`, `log`, `feedback`,
  `config`, `frameworks`.

**Adding a skill** = a new module in `cpl/skills/` exposing
`SKILL = Skill(name=..., run=run, hook=?/command=?)`, plus one line in
`registry._SKILL_MODULES`. No dispatcher changes.

## Commit & PR conventions

- Conventional commit prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Keep PRs focused. Describe what changed and how you verified it.
- Be kind and assume good intent (see the Code of Conduct).

## Reporting security issues

Please do **not** open a public issue for vulnerabilities — see
[SECURITY.md](SECURITY.md).
