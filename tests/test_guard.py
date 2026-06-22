"""Tests for the PreToolUse secret-in-context guard (stdlib unittest).

Covers: sensitive-name gate, transient content scan + decision, mode switch
(warn/ask/deny/off), low-false-positive (sensitive name but no secret -> allow),
Bash inline-secret and read-verb cases, and fail-open on malformed payloads.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.registry import Context  # noqa: E402
from cpl.skills import guard  # noqa: E402

_PRIVATE_KEY = ("-----BEGIN RSA PRIVATE KEY-----\n"
                "MIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----")
_CONN = "postgres://admin:s3cr3tpassword@db.example.com:5432/prod"


def _ctx(tool, tool_input, cwd, mode="warn"):
    return Context(prompt="", cwd=str(cwd), config={"guard": {"mode": mode}},
                   event="PreToolUse", log_path=None,
                   payload={"tool_name": tool, "tool_input": tool_input})


class ReadGuard(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def _env_with(self, content):
        p = self.d / ".env"
        p.write_text(content, encoding="utf-8")
        return ".env"

    def test_ordinary_file_passes_without_scan(self):
        (self.d / "app.py").write_text(_PRIVATE_KEY, encoding="utf-8")  # secret, but…
        # …an ordinary name must not even be scanned -> pass.
        res = guard.run(_ctx("Read", {"file_path": "app.py"}, self.d))
        self.assertEqual(res.action, "pass")

    def test_env_with_secret_warns_by_default(self):
        self._env_with(_PRIVATE_KEY)
        res = guard.run(_ctx("Read", {"file_path": ".env"}, self.d))
        self.assertEqual(res.action, "inject")
        self.assertIn("secret", res.payload.lower())

    def test_mode_ask_blocks_with_ask_decision(self):
        self._env_with(_PRIVATE_KEY)
        res = guard.run(_ctx("Read", {"file_path": ".env"}, self.d, mode="ask"))
        self.assertEqual(res.action, "block")
        self.assertEqual(res.meta.get("decision"), "ask")

    def test_mode_deny_blocks_with_deny_decision(self):
        self._env_with(_PRIVATE_KEY)
        res = guard.run(_ctx("Read", {"file_path": ".env"}, self.d, mode="deny"))
        self.assertEqual(res.action, "block")
        self.assertEqual(res.meta.get("decision"), "deny")

    def test_sensitive_name_but_no_secret_passes(self):
        self._env_with("PORT=8080\nDEBUG=true\n")  # no actual secret
        res = guard.run(_ctx("Read", {"file_path": ".env"}, self.d))
        self.assertEqual(res.action, "pass")

    def test_missing_file_passes(self):
        res = guard.run(_ctx("Read", {"file_path": ".env"}, self.d))  # never created
        self.assertEqual(res.action, "pass")

    def test_mode_off_passes_even_with_secret(self):
        self._env_with(_PRIVATE_KEY)
        res = guard.run(_ctx("Read", {"file_path": ".env"}, self.d, mode="off"))
        self.assertEqual(res.action, "pass")


class BashGuard(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_inline_secret_in_command_warns(self):
        res = guard.run(_ctx("Bash", {"command": f'psql {_CONN}'}, self.d))
        self.assertEqual(res.action, "inject")

    def test_cat_of_env_file_warns(self):
        res = guard.run(_ctx("Bash", {"command": "cat .env | grep KEY"}, self.d))
        self.assertEqual(res.action, "inject")

    def test_grep_of_env_file_warns(self):
        res = guard.run(_ctx("Bash", {"command": "grep SECRET .env"}, self.d))
        self.assertEqual(res.action, "inject")

    def test_bare_env_dump_warns(self):
        for cmd in ("env", "printenv", "env | sort"):
            res = guard.run(_ctx("Bash", {"command": cmd}, self.d))
            self.assertEqual(res.action, "inject", cmd)

    def test_env_as_command_prefix_passes(self):
        # `env VAR=1 cmd` runs a command in a modified env — not a dump.
        res = guard.run(_ctx("Bash", {"command": "env NODE_ENV=test npm test"}, self.d))
        self.assertEqual(res.action, "pass")

    def test_ordinary_command_passes(self):
        res = guard.run(_ctx("Bash", {"command": "ls -la && git status"}, self.d))
        self.assertEqual(res.action, "pass")

    def test_grep_of_ordinary_file_passes(self):
        res = guard.run(_ctx("Bash", {"command": "grep TODO src/app.py"}, self.d))
        self.assertEqual(res.action, "pass")


class FailOpen(unittest.TestCase):
    def test_malformed_tool_input_passes(self):
        ctx = Context(prompt="", cwd=".", config={"guard": {"mode": "deny"}},
                      event="PreToolUse", payload={"tool_name": "Read",
                                                   "tool_input": "not-a-dict"})
        self.assertEqual(guard.run(ctx).action, "pass")

    def test_empty_payload_passes(self):
        ctx = Context(prompt="", config={}, event="PreToolUse", payload={})
        self.assertEqual(guard.run(ctx).action, "pass")


if __name__ == "__main__":
    unittest.main()
