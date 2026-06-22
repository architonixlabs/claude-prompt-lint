"""guard skill — PreToolUse secret-in-context guard.

The gate (UserPromptSubmit) only sees the prompt the user *typed*. The bigger
leak vector in agentic coding is the assistant reading a secret-bearing file
(`.env`, `*.pem`, `id_rsa`, …) into context on its own — a `Read`/`Bash` cpl
never saw. This guard sits on `PreToolUse`, the instant before that read runs.

Design rules (see docs/design/pretooluse-secret-guard.md):
  * STATELESS — scan transiently, decide, discard. Never persist findings or
    index where secrets live (that index would *be* the breach).
  * FAIL-OPEN (sacred) — any error defers to "allow"; a guard bug must never
    freeze the assistant.
  * LOW FALSE-POSITIVE — a cheap filename gate first; only content-scan files
    whose name looks sensitive, and only act when a real secret is found.
  * METADATA-ONLY logging — kinds + tool + action, never the value or path.

Returns a Result the dispatcher maps to the PreToolUse contract:
  action="block" + meta["decision"] in {"ask","deny"}  -> interrupt the tool
  action="inject" (payload=note)                        -> warn, tool proceeds
  action="pass"                                         -> allow
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, List

from cpl.registry import Context, Result, Skill
from cpl.shared import log, secrets

_DEFAULT_GLOBS = [
    ".env", ".env.*", "*.env",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "*credential*", "*credentials*", "*secret*", "*.secrets",
    "*.ovpn", ".npmrc", ".pypirc", ".netrc",
]
_DEFAULT_MAX_BYTES = 200_000
# Bash verbs that would surface a file's contents into the conversation.
_READ_VERBS = ("cat", "head", "tail", "less", "more", "bat", "type", "xxd",
               "od", "strings", "grep", "egrep", "rg", "ag", "awk", "sed",
               "cut", "sort", "uniq", "nl", "tac", "base64", "tee")
# Verbs that dump the whole environment (often full of secrets) to stdout.
_ENV_DUMP_VERBS = ("env", "printenv")


def _guard_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    g = cfg.get("guard")
    return g if isinstance(g, dict) else {}


def _globs(gcfg: Dict[str, Any]) -> List[str]:
    globs = gcfg.get("sensitive_globs")
    return globs if isinstance(globs, list) and globs else _DEFAULT_GLOBS


def _name_is_sensitive(path: str, globs: List[str]) -> bool:
    base = os.path.basename(path.strip().strip('"').strip("'")).lower()
    if not base:
        return False
    return any(fnmatch.fnmatch(base, g.lower()) for g in globs)


def _scan_file(path: Path, cfg: Dict[str, Any], max_bytes: int):
    """Transiently read + scan a file. Returns findings (block-severity only)."""
    try:
        if not path.is_file():
            return []
        data = path.read_bytes()[:max_bytes]
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return []
    findings = secrets.scan(text, cfg)
    return [f for f in findings if f.severity == secrets.BLOCK]


def _kinds(findings) -> str:
    seen = []
    for f in findings:
        if f.kind not in seen:
            seen.append(f.kind)
    return ", ".join(seen) or "secret"


def _decision_for_mode(mode: str):
    """Map config mode -> (action, decision) the dispatcher understands."""
    if mode == "deny":
        return ("block", "deny")
    if mode == "ask":
        return ("block", "ask")
    return ("inject", None)  # "warn"


def _log(ctx: Context, tool: str, action: str, kinds: str) -> None:
    if ctx.log_path is None:
        return
    try:
        log.append(ctx.log_path, {
            "event": "guard",
            "tool": tool,
            "action": action,         # ask | deny | warn
            "kinds": kinds,           # detector kinds only — never the value/path
        })
    except Exception:
        pass


def _result(ctx, mode, tool, where, kinds) -> Result:
    action, decision = _decision_for_mode(mode)
    reason = (
        f"cpl guard: this {tool} would expose what looks like a secret "
        f"({kinds}) {where}. Confirm before letting it into the conversation, "
        f"or mask/move the value. (tune guard.mode = warn|ask|deny|off in "
        f"~/.cpl/config.json)"
    )
    _log(ctx, tool, "warn" if action == "inject" else decision, kinds)
    return Result(action=action, payload=reason,
                  meta={"skill": "guard", "decision": decision, "kinds": kinds})


def run(ctx: Context) -> Result:
    cfg = ctx.config or {}
    gcfg = _guard_cfg(cfg)

    # Disabled / off -> allow. (Default mode is the lenient "warn".)
    mode = str(gcfg.get("mode", "warn")).lower()
    if mode == "off":
        return Result(action="pass", meta={"skill": "guard", "reason": "off"})

    payload = ctx.payload or {}
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return Result(action="pass")  # unknown shape -> fail-open

    globs = _globs(gcfg)
    max_bytes = int(gcfg.get("max_scan_bytes", _DEFAULT_MAX_BYTES) or _DEFAULT_MAX_BYTES)
    root = Path(ctx.cwd or os.getcwd())

    try:
        # --- Read: scan the target file iff its name looks sensitive. ---
        if tool == "Read":
            fp = tool_input.get("file_path") or tool_input.get("path") or ""
            if not fp or not _name_is_sensitive(fp, globs):
                return Result(action="pass")
            target = Path(fp) if os.path.isabs(fp) else (root / fp)
            findings = _scan_file(target, cfg, max_bytes)
            if findings:
                return _result(ctx, mode, "read", "into the assistant's context",
                               _kinds(findings))
            return Result(action="pass")

        # --- Bash: inline secret in the command, or reading a sensitive file. ---
        if tool == "Bash":
            command = tool_input.get("command") or ""
            if not isinstance(command, str) or not command:
                return Result(action="pass")
            # (a) a literal secret pasted into the command itself
            inline = [f for f in secrets.scan(command, cfg) if f.severity == secrets.BLOCK]
            if inline:
                return _result(ctx, mode, "command", "in the command", _kinds(inline))
            toks = command.replace("|", " ").replace(";", " ").replace("&", " ").split()
            lowered = [t.lower() for t in toks]
            # (b) a bare env dump (`env` / `printenv` with no `VAR=...` prefix,
            #     which would instead be running a command in a modified env).
            if lowered and lowered[0] in _ENV_DUMP_VERBS \
                    and not any("=" in t for t in toks[1:]):
                return _result(ctx, mode, "command",
                               "by dumping environment variables", "env vars")
            # (c) a read verb pointed at a sensitive-looking file
            if set(lowered) & set(_READ_VERBS):
                for t in toks[1:]:
                    if _name_is_sensitive(t, globs):
                        return _result(ctx, mode, "command",
                                       "by printing a secret file", "secret file")
            return Result(action="pass")

        # --- Write/Edit: catch hardcoding a secret INTO a file. ---
        if tool in ("Write", "Edit"):
            content = tool_input.get("new_string") if tool == "Edit" \
                else tool_input.get("content")
            if not isinstance(content, str) or not content:
                return Result(action="pass")
            found = [f for f in secrets.scan(content, cfg)
                     if f.severity == secrets.BLOCK]
            if found:
                fp = tool_input.get("file_path") or ""
                where = (f"by writing it to {os.path.basename(fp)}" if fp
                         else "by writing it to a file")
                return _result(ctx, mode, tool.lower(), where, _kinds(found))
            return Result(action="pass")

        # Any other tool slipped past the matcher -> allow.
        return Result(action="pass")
    except Exception:
        # Sacred fail-open: never block a tool because of a guard bug.
        return Result(action="pass", meta={"skill": "guard", "error": True})


SKILL = Skill(name="guard", run=run, hook="PreToolUse")
