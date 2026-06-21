# claude-prompt-lint — dev image (Linux).
#
# Honest scope: cpl is a Claude Code *plugin*, not a network service, so this
# image does NOT run a server. Its job is to (1) build on Linux, (2) self-verify
# with the test suite + gate eval, and (3) let you exercise the dispatcher CLI on
# Linux. Pure standard library — the only dependency is a Python interpreter.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="claude-prompt-lint (dev)" \
      org.opencontainers.image.description="Local-first prompt-quality toolkit for Claude Code — dev/self-check image." \
      org.opencontainers.image.source="https://github.com/architonixlabs/claude-prompt-lint" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CLAUDE_PLUGIN_ROOT=/app

WORKDIR /app
COPY . /app

# Build-time self-check: a syntax error anywhere fails the build, not runtime.
RUN python -m compileall -q cpl hooks eval tests

# Default command is the dev smoke test: full unit suite + gate eval. The eval
# step is wrapped so a non-zero false-positive rate fails the container (exit 1).
# Override to drive the CLI instead, e.g.:
#   docker run --rm claude-prompt-lint-dev python hooks/dispatcher.py --command help
#   echo '{"prompt":"fix it"}' | docker run --rm -i claude-prompt-lint-dev \
#       python hooks/dispatcher.py --event UserPromptSubmit
CMD ["sh", "-lc", "python -m unittest discover -s tests -q && python eval/run_eval.py | tee /tmp/eval.out && ! (grep -E 'False Positive Rate' /tmp/eval.out | grep -qvE ':\\s+0\\.0%')"]
