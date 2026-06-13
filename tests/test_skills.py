"""Smoke + behavior tests for the command skills and dispatcher routing.

Pure stdlib (unittest) — the plugin has zero dependencies and these keep it
that way. Run from the repo root:  python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make the `cpl` package and the dispatcher importable from the repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.registry import Context, Registry  # noqa: E402
from cpl.skills import gate  # noqa: E402
from cpl.shared import rules  # noqa: E402

import importlib  # noqa: E402

dispatcher = importlib.import_module("hooks.dispatcher")


def _cfg(**over):
    base = {
        "enabled": True,
        "mode": "warn",
        "bypass_prefix": "!!",
        "min_length_skip": 40,
        "block_threshold": 50,
        "use_model": False,
    }
    base.update(over)
    return base


class CommandSkillSmoke(unittest.TestCase):
    """Every command skill runs, returns a message, and never raises."""

    def setUp(self):
        self.cfg = _cfg()
        self.reg = Registry(self.cfg)
        self.tmp = Path(tempfile.mktemp(suffix=".jsonl"))

    def tearDown(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def _ctx(self, args):
        return Context(prompt=args, args=args, cwd=str(_ROOT), config=self.cfg,
                       log_path=self.tmp, event="command")

    def test_all_command_skills_produce_output(self):
        samples = {
            "rewrite": "fix the login bug",
            "explain": "make it better",
            "scope": "check README.md and nope.py",
            "stats": "",
            "profile": "",
            "expand": "add caching",
            "template": "",
        }
        for cmd, arg in samples.items():
            skill = self.reg.for_command(cmd)
            self.assertIsNotNone(skill, f"{cmd} not registered")
            res = skill.run(self._ctx(arg))  # must not raise
            self.assertEqual(res.action, "message", f"{cmd} action")
            self.assertTrue(res.payload.strip(), f"{cmd} produced no output")


class DispatcherRouting(unittest.TestCase):
    def setUp(self):
        self.cfg = _cfg()

    def test_help_lists_commands(self):
        out = []
        dispatcher._write = lambda t: (out.append(t) or 0)  # capture
        dispatcher.handle_command("help", "", self.cfg)
        self.assertIn("Commands", out[0])

    def test_unknown_command_is_graceful(self):
        out = []
        dispatcher._write = lambda t: (out.append(t) or 0)
        dispatcher.handle_command("bogus", "", self.cfg)
        self.assertIn("Unknown", out[0])

    def test_bare_command_routes_to_help(self):
        out = []
        dispatcher._write = lambda t: (out.append(t) or 0)
        dispatcher.handle_command("", "", self.cfg)
        self.assertIn("lint your prompt", out[0].lower())

    def test_command_args_preserves_skill_flags(self):
        # Regression: argparse used to divert `--quick` into 'unknown' and drop
        # it. The skill must receive flags verbatim.
        got = dispatcher._command_args(
            ["--command", "expand", "--quick", "race", "fix", "login"])
        self.assertEqual(got, "--quick race fix login")

    def test_quick_flag_survives_full_dispatch(self):
        # End-to-end through main(): --quick must force a one-shot render, not
        # the interactive CPL_EXPAND_SPEC block.
        out = []
        dispatcher._write = lambda t: (out.append(t) or 0)
        dispatcher.main(["--command", "expand", "--quick", "race", "fix login"])
        payload = "".join(out)
        self.assertNotIn("CPL_EXPAND_SPEC", payload)
        self.assertIn("Role", payload)  # race scaffold label


class GateBehavior(unittest.TestCase):
    def test_bypass_prefix_passes(self):
        ctx = Context(prompt="!! anything at all goes here past the length skip",
                      config=_cfg(), event="UserPromptSubmit")
        self.assertEqual(gate.run(ctx).action, "pass")

    def test_short_prompt_passes(self):
        ctx = Context(prompt="hi there", config=_cfg(), event="UserPromptSubmit")
        self.assertEqual(gate.run(ctx).action, "pass")

    def test_good_prompt_passes(self):
        good = ("In auth.py, parseToken() throws KeyError when the JWT has no "
                "exp claim. Add a guard and a test in test_auth.py.")
        ctx = Context(prompt=good, config=_cfg(), event="UserPromptSubmit")
        self.assertEqual(gate.run(ctx).action, "pass")

    def test_weak_prompt_blocks_in_block_mode(self):
        weak = ("can you please just go ahead and fix it and make the whole "
                "thing better for me right now today")
        ctx = Context(prompt=weak, config=_cfg(mode="block"),
                      event="UserPromptSubmit")
        res = gate.run(ctx)
        self.assertEqual(res.action, "block")
        # The block reason must be valid JSON when emitted.
        payload = json.dumps({"decision": "block", "reason": res.payload})
        self.assertIn("decision", json.loads(payload))

    def test_fail_open_when_rules_raise(self):
        original = rules.evaluate
        rules.evaluate = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            ctx = Context(prompt="a" * 80, config=_cfg(),
                          event="UserPromptSubmit")
            self.assertEqual(gate.run(ctx).action, "pass")  # never blocks
        finally:
            rules.evaluate = original


if __name__ == "__main__":
    unittest.main()
