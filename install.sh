#!/usr/bin/env bash
# claude-prompt-lint installer (POSIX).
# This plugin is pure-Python with zero pip dependencies. "Installing" means:
#   1. confirm a Python 3.8+ interpreter is on PATH (the hook command uses it),
#   2. run a self-check so you know the gate works before you rely on it.
#
# To use it in Claude Code, add this repo as a plugin (see README).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "claude-prompt-lint — install check"
echo "  repo: $ROOT"

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "  ✗ No python on PATH. Install Python 3.8+ and re-run." >&2
  exit 1
fi
echo "  ✓ python: $("$PY" --version 2>&1)"

echo "  running self-check (a weak prompt should be flagged)…"
OUT="$(printf '{"prompt":"can you please just go ahead and fix it and make this better for me"}' \
  | "$PY" "$ROOT/hooks/dispatcher.py" --event UserPromptSubmit || true)"
if [ -n "$OUT" ]; then
  echo "  ✓ gate produced feedback. Self-check passed."
else
  echo "  ⚠ gate produced no output for a weak prompt. Check config/cpl.config.json."
fi

echo ""
echo "Next: register the plugin in Claude Code (see README → Install)."
echo "Lint your prompt before you spend the token."
