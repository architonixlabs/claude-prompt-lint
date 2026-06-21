<!-- Thanks for contributing to claude-prompt-lint! -->

## What & why

<!-- One or two sentences: what does this change and why? -->

## How verified

<!-- Commands you ran and what you observed. -->

- [ ] `python3 -m unittest discover -s tests` — all pass
- [ ] `python3 eval/run_eval.py` — **False Positive Rate 0.0%**
- [ ] `python3 -m compileall -q cpl hooks eval tests` — clean

## Checklist

- [ ] No new dependencies (standard library only)
- [ ] Fail-open preserved (nothing from the hook can block/crash a prompt)
- [ ] No prompt text or secret values written to logs
- [ ] Added/updated tests (regression guard if fixing a bug)
- [ ] Updated `CHANGELOG.md`
- [ ] Bumped version in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `cpl/__init__.py` (if releasing)
