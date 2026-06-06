"""Tier 2 local-model client (Ollama JSON contract).

Uses only the standard library (urllib) so the plugin has zero pip deps.

Contract — the model is forced to return JSON of the shape:
    {"pass": bool, "score": int, "issues": [str], "suggestions": [str]}

Sacred rule: FAIL-OPEN. Any error, timeout, malformed response, or model
being down returns None, and the caller treats None as "pass / inconclusive".
The checker must never block the user because the local model misbehaved.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

_SYSTEM = (
    "You are a terse prompt-quality rater for a software engineering assistant. "
    "Given a user's prompt, judge whether it is specific enough to act on without "
    "a clarification round-trip. Look for: missing file/symbol referents, dangling "
    "pronouns, no acceptance criteria, ambiguous scope, missing constraints. "
    "Be lenient — only flag prompts that would genuinely need a follow-up question. "
    "Do not rewrite the prompt. Respond with JSON only."
)

_RUBRIC = (
    "Return JSON exactly of this shape and nothing else:\n"
    '{"pass": <true|false>, "score": <0-100 weakness, 0=perfect>, '
    '"issues": ["short bullet", ...], "suggestions": ["actionable hint", ...]}\n'
    "Keep issues and suggestions to at most 3 each, one short sentence apiece."
)


def _build_prompt(user_prompt: str) -> str:
    return (
        f"{_SYSTEM}\n\n{_RUBRIC}\n\n"
        f"USER PROMPT TO RATE:\n<<<\n{user_prompt.strip()}\n>>>\n\nJSON:"
    )


def _port_open(endpoint: str, timeout_s: float) -> bool:
    """Fast pre-flight: is anything listening at the endpoint's host:port?

    On Windows, a POST to a closed port triggers ~3s of TCP connect retries
    before urlopen's read-timeout applies — so "Ollama is off" would tax every
    inconclusive prompt. A short connect probe lets us fail open instantly
    instead. Any uncertainty returns True so we still attempt the real call.
    """
    try:
        parsed = urllib.parse.urlparse(endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False
    except Exception:
        return True  # don't let a probe bug suppress a working endpoint


def evaluate(
    user_prompt: str,
    endpoint: str,
    model: str,
    timeout_ms: int,
) -> Optional[Dict[str, Any]]:
    """Call the local model. Returns a normalized dict or None (fail-open)."""
    timeout_s = max(0.2, timeout_ms / 1000.0)

    # Pre-flight connect probe (capped well under the full budget) so a closed
    # port fails open in ~ms instead of waiting out OS connect retries.
    if not _port_open(endpoint, timeout_s=min(0.4, timeout_s)):
        return None

    body = {
        "model": model,
        "prompt": _build_prompt(user_prompt),
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": 256,
        },
    }

    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    except Exception:
        return None

    return _parse(raw)


def _parse(raw: str) -> Optional[Dict[str, Any]]:
    """Parse the Ollama envelope, then the inner JSON verdict. Fail-open."""
    try:
        envelope = json.loads(raw)
    except Exception:
        return None

    # /api/generate returns {"response": "<the model text>", ...}
    inner_text = envelope.get("response") if isinstance(envelope, dict) else None
    if not isinstance(inner_text, str):
        return None

    try:
        verdict = json.loads(inner_text)
    except Exception:
        return None
    if not isinstance(verdict, dict):
        return None

    return _normalize(verdict)


def _normalize(v: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce the model's verdict into the strict contract shape.

    Small models drift from the contract — e.g. returning issues as a list of
    objects ({"message": ..., "severity": ...}) instead of strings. We extract
    the human-readable text from common key names rather than stringifying the
    whole dict.
    """
    def _item_text(i: Any) -> str:
        if isinstance(i, str):
            return i.strip()
        if isinstance(i, dict):
            for key in ("message", "text", "issue", "suggestion", "detail",
                        "description", "msg"):
                val = i.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            # No known key — fall back to the first string value present.
            for val in i.values():
                if isinstance(val, str) and val.strip():
                    return val.strip()
            return ""
        return str(i).strip()

    def _str_list(x: Any) -> list:
        if isinstance(x, list):
            return [t for t in (_item_text(i) for i in x) if t][:3]
        if isinstance(x, str) and x.strip():
            return [x.strip()]
        return []

    score = v.get("score", 0)
    try:
        score = int(round(float(score)))
    except Exception:
        score = 0
    score = max(0, min(100, score))

    passed = v.get("pass")
    if not isinstance(passed, bool):
        # Infer from score if the model omitted/garbled `pass`.
        passed = score < 50

    return {
        "pass": passed,
        "score": score,
        "issues": _str_list(v.get("issues")),
        "suggestions": _str_list(v.get("suggestions")),
    }
