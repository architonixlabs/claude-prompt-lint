#!/usr/bin/env sh
# Portable launcher for the cpl dispatcher (POSIX shells: Linux, macOS, Git Bash).
# Finds a working Python 3 interpreter, then forwards all args + stdin to the
# dispatcher. Fail-open: if no interpreter is found we exit 0 with no output so
# the user's prompt is never blocked by a missing dependency.

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

for PY in python3 python py; do
  if command -v "$PY" >/dev/null 2>&1; then
    exec "$PY" "$DIR/dispatcher.py" "$@"
  fi
done

# No Python found — fail open (empty stdout, exit 0).
exit 0
