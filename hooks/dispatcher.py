#!/usr/bin/env python3
"""cpl dispatcher — entry point for hook events and /cpl commands.

Invoked two ways:

  Hook (UserPromptSubmit):
      python dispatcher.py --event UserPromptSubmit
      stdin = JSON with a "prompt" field (Claude Code hook payload).

  Command (/cpl <skill> <args>):
      python dispatcher.py --command <skill> [args...]
      (Wired through commands/cpl.md.)

Hook output contract (Claude Code, verified mid-2026 — re-check on upgrade):
  * PASS    : exit 0, empty stdout.
  * BLOCK   : exit 0, stdout = {"decision":"block","reason":"..."}.
  * INJECT  : exit 0, stdout = plain text -> appended to context (warn mode).

SACRED: fail-open. Any unexpected error -> exit 0 with empty stdout so the
user's prompt always proceeds. A broken gate must never block work.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

# Force UTF-8 on stdout/stderr so feedback (which may contain ⛔ ⚠️ → etc.)
# renders on Windows consoles too (default there is cp1252). Best-effort.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # py3.7+
    except Exception:
        pass

# Make the package importable whether invoked as a script or module.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cpl.shared import config as config_mod  # noqa: E402


def _debug(cfg, msg: str) -> None:
    if not cfg.get("debug_log"):
        return
    try:
        log_path = config_mod.resolve_log_path(cfg)
        dbg = log_path.parent / "cpl-debug.log"
        with dbg.open("a", encoding="utf-8") as fh:
            fh.write(msg.rstrip() + "\n")
    except Exception:
        pass


def _safe_cfg() -> dict:
    """Load config but never raise — used in last-resort fallbacks."""
    try:
        return config_mod.load_config()
    except Exception:
        return {}


def _read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _emit_pass() -> int:
    # Empty stdout, exit 0 -> prompt proceeds.
    return 0


def _write(text: str) -> int:
    # Single point that writes stdout and flushes, so a clean exit can never
    # leave a partially-buffered (and unparseable) block/JSON payload.
    sys.stdout.write(text)
    try:
        sys.stdout.flush()
    except Exception:
        pass
    return 0


def _emit_block(reason: str) -> int:
    return _write(json.dumps({"decision": "block", "reason": reason}))


def _emit_inject(text: str) -> int:
    # Plain text on stdout is appended to context.
    return _write(text)


def _emit_message(text: str) -> int:
    # Command output -> shown to the user.
    return _write(text)


def _emit_pre_tool_decision(decision: str, reason: str) -> int:
    # PreToolUse interrupt: "deny" blocks the tool, "ask" forces a permission
    # prompt. The reason is shown to Claude / the user.
    return _write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))


def _emit_pre_tool_context(text: str) -> int:
    # PreToolUse non-blocking warning: surface context, let the tool proceed.
    return _write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": text,
        }
    }))


def handle_hook(event: str, cfg) -> int:
    from cpl.registry import Context, Registry

    payload = _read_stdin_json()
    # Field name has varied across Claude Code versions: "prompt" vs
    # "user_prompt". Accept either so the gate keeps working on upgrade.
    prompt = payload.get("prompt")
    if prompt is None:
        prompt = payload.get("user_prompt", "")
    if not isinstance(prompt, str):
        prompt = str(prompt or "")

    # M0 smoke trail: record raw payload shape when debugging.
    _debug(cfg, f"[hook] event={event} keys={sorted(payload.keys())} "
                f"prompt_len={len(prompt)}")

    log_path = config_mod.resolve_log_path(cfg)
    cwd = payload.get("cwd") or os.getcwd()

    registry = Registry(cfg)
    skills = registry.for_hook(event)
    if not skills:
        return _emit_pass()

    ctx = Context(
        prompt=prompt,
        cwd=cwd,
        config=cfg,
        log_path=log_path,
        event=event,
    )

    # Run hook skills in order. First skill that blocks wins; inject messages
    # accumulate; otherwise pass.
    inject_chunks = []
    for skill in skills:
        try:
            result = skill.run(ctx)
        except Exception as exc:
            _debug(cfg, f"[hook] skill {skill.name} error: {exc}\n"
                        f"{traceback.format_exc()}")
            continue  # fail-open per skill

        if result.action == "block":
            return _emit_block(result.payload)
        if result.action == "inject" and result.payload:
            inject_chunks.append(result.payload)
        # "pass" / "message" from a hook skill -> nothing to emit here.

    if inject_chunks:
        return _emit_inject("\n".join(inject_chunks))
    return _emit_pass()


def handle_pre_tool(event: str, cfg) -> int:
    """PreToolUse: guard tool calls (e.g. reading a secret file) before they run.

    Distinct from handle_hook: the input is a tool payload (tool_name/tool_input)
    and the output contract is the permissionDecision JSON, not block/inject.
    Fail-open: empty stdout (exit 0) lets the tool proceed.
    """
    from cpl.registry import Context, Registry

    payload = _read_stdin_json()
    cwd = payload.get("cwd") or os.getcwd()
    _debug(cfg, f"[pretool] tool={payload.get('tool_name')} "
                f"keys={sorted(payload.keys())}")

    skills = Registry(cfg).for_hook(event)
    if not skills:
        return _emit_pass()

    log_path = config_mod.resolve_log_path(cfg)
    ctx = Context(prompt="", cwd=cwd, config=cfg, log_path=log_path,
                  event=event, payload=payload)

    for skill in skills:
        try:
            result = skill.run(ctx)
        except Exception as exc:
            _debug(cfg, f"[pretool] skill {skill.name} error: {exc}\n"
                        f"{traceback.format_exc()}")
            continue  # fail-open per skill
        if result.action == "block":
            decision = result.meta.get("decision") or "ask"
            return _emit_pre_tool_decision(decision, result.payload)
        if result.action == "inject" and result.payload:
            return _emit_pre_tool_context(result.payload)
        # "pass" -> let the next skill speak / allow.
    return _emit_pass()


def handle_command(command: str, args: str, cfg) -> int:
    from cpl.registry import Context, Registry

    registry = Registry(cfg)

    if not command or command in ("help", "--help", "-h"):
        cmds = ", ".join(registry.commands()) or "(none enabled)"
        enabled = cfg.get("enabled", True)
        mode = cfg.get("mode", "warn")
        bypass = cfg.get("bypass_prefix", "!!")
        model = "on" if cfg.get("use_model", False) else "off"
        return _emit_message(
            "cpl — the last thing that runs on your machine before a prompt leaves it.\n"
            "\n"
            "Locally, before any token is spent or data leaves your machine: catch\n"
            "secrets, keep your repo legible to Claude (/cpl init), and tighten weak\n"
            "prompts as an offer, not a scold. Most prompts pass instantly.\n"
            "\n"
            f"  Status   : gate {'enabled' if enabled else 'DISABLED'}, "
            f"mode={mode}, model tier {model}\n"
            f"  Bypass   : start a prompt with `{bypass}` to skip the gate once\n"
            f"  Off      : put {{\"enabled\": false}} in ~/.cpl/config.json\n"
            "\n"
            f"  Commands : {cmds}\n"
            "  Usage    : /cpl <command> [args]\n"
            "\n"
            "  e.g.  /cpl explain make the dashboard better\n"
            "        /cpl rewrite fix the login bug\n"
            "        /cpl stats        /cpl profile\n"
            "\n"
            "Full docs: https://github.com/architonixlabs/claude-prompt-lint"
        )

    skill = registry.for_command(command)
    if skill is None:
        cmds = ", ".join(registry.commands()) or "(none enabled)"
        return _emit_message(
            f"[cpl] Unknown or disabled command: '{command}'. Available: {cmds}"
        )

    log_path = config_mod.resolve_log_path(cfg)
    ctx = Context(
        prompt=args,
        args=args,
        cwd=os.getcwd(),
        config=cfg,
        log_path=log_path,
        event="command",
    )
    try:
        result = skill.run(ctx)
    except Exception as exc:
        _debug(cfg, f"[command] skill {skill.name} error: {exc}\n"
                    f"{traceback.format_exc()}")
        return _emit_message(f"[cpl] '{command}' failed (fail-open). See debug log.")

    if result.action in ("message", "inject", "block"):
        return _emit_message(result.payload)
    return _emit_message("[cpl] (no output)")


def _command_args(argv) -> str:
    """The literal arg string after `--command <skill>`.

    We extract this from raw argv rather than argparse REMAINDER because
    argparse diverts skill flags like `--quick` into 'unknown' and drops them.
    Everything after the skill token is the skill's args, flags included.
    """
    if "--command" not in argv:
        return ""
    after = argv[argv.index("--command") + 1:]   # [skill, *args]
    return " ".join(after[1:]).strip()           # drop the skill token


def main(argv=None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="cpl-dispatcher", add_help=False)
    parser.add_argument("--event", default=None)
    # nargs="?" so a bare `--command` (empty $ARGUMENTS when the user types just
    # `/cpl`) routes to help instead of an argparse error.
    parser.add_argument("--command", nargs="?", default=None, const="")
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    try:
        ns, _unknown = parser.parse_known_args(raw_argv)
    except SystemExit:
        # argparse calls sys.exit on parse errors; never let that surface as a
        # crash. Fall back to help (command) / pass (hook is unaffected here).
        return handle_command("help", "", _safe_cfg())

    try:
        cfg = config_mod.load_config()
    except Exception:
        # Even config load failing must not block the prompt.
        return _emit_pass()

    try:
        if ns.event:
            if ns.event == "PreToolUse":
                return handle_pre_tool(ns.event, cfg)
            return handle_hook(ns.event, cfg)
        if ns.command is not None:
            # Take args from raw argv so skill flags (e.g. --quick) survive.
            args = _command_args(raw_argv)
            return handle_command(ns.command.strip(), args, cfg)
        # No mode specified -> treat as help.
        return handle_command("help", "", cfg)
    except Exception as exc:
        # Last-resort fail-open. Hook path must stay silent; command path can note it.
        if ns.event:
            _debug(cfg, f"[fatal-hook] {exc}\n{traceback.format_exc()}")
            return _emit_pass()
        return _emit_message(f"[cpl] error (fail-open): {exc}")


if __name__ == "__main__":
    sys.exit(main())
