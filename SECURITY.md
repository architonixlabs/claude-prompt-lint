# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public GitHub issue.

Email **rcsamal@gmail.com** with:

- a description of the issue and its impact,
- steps to reproduce (a minimal prompt or config is ideal),
- the plugin version (`cpl/__init__.py` `__version__` or the installed
  marketplace version).

You'll get an acknowledgement as soon as possible. Please give a reasonable
window to address the issue before any public disclosure.

## Supported versions

Fixes land on the latest minor release. Please reproduce against the most recent
version before reporting.

| Version | Supported |
|---------|-----------|
| latest `1.x` | ✅ |
| older | ❌ (please upgrade) |

## Scope & expectations

`cpl` runs **entirely on your machine** and makes no network calls except to a
**local** model endpoint (Ollama, only if you enable it). It does not transmit
your prompts or logs anywhere. Relevant classes of report:

- A way to make the `UserPromptSubmit` hook **block or crash a legitimate
  prompt** (a fail-open violation).
- A path where a **detected secret value is written to disk or echoed** (the
  data-masking feature must store/echo masked previews and detector *kinds*
  only, never raw secret values).
- A **catastrophic-backtracking regex** reachable from the hook.

### Important: data masking is best-effort, not a guarantee

The data-masking feature (`/cpl mask`, automatic secret detection) reduces the
chance of accidentally sending a secret, but it is a **heuristic local filter**,
not a security boundary. It deliberately omits high-false-positive detectors and
will miss novel or obfuscated secrets. **Do not rely on it as your only control**
for keeping credentials out of prompts. Rotate any secret you believe was
exposed.
