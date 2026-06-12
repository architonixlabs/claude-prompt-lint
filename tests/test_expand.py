"""Tests for the expand skill's framework parsing and modes (stdlib unittest)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.registry import Context  # noqa: E402
from cpl.skills import expand  # noqa: E402


def _ctx(args, **cfg):
    base = {"use_model": False, "expand": {"interactive": True,
            "default_framework": "default", "tone": "neutral",
            "verbosity": "concise"}}
    base.update(cfg)
    return Context(prompt=args, args=args, config=base, event="command")


class Parsing(unittest.TestCase):
    def test_no_args_lists_frameworks(self):
        out = expand.run(_ctx("")).payload
        self.assertIn("available frameworks", out.lower())
        self.assertIn("race", out)

    def test_named_framework_is_consumed(self):
        # interactive spec should name RACE and carry the remaining prompt
        out = expand.run(_ctx("race fix the login bug")).payload
        self.assertIn("framework: race", out)
        self.assertIn("framework_named: true", out)
        self.assertIn("prompt: fix the login bug", out)

    def test_unknown_first_word_is_prompt(self):
        out = expand.run(_ctx("fix the race condition")).payload
        self.assertIn("framework: default", out)
        self.assertIn("framework_named: false", out)
        self.assertIn("prompt: fix the race condition", out)

    def test_framework_name_only_no_prompt(self):
        out = expand.run(_ctx("race")).payload
        self.assertIn("framework: race", out)
        self.assertIn("prompt:", out)   # empty prompt line is valid


class Modes(unittest.TestCase):
    def test_quick_flag_forces_static_scaffold(self):
        cfg = {"use_model": False,
               "expand": {"interactive": True, "default_framework": "default"}}
        out = expand.run(Context(prompt="--quick add caching",
                                 args="--quick add caching", config=cfg,
                                 event="command")).payload
        # one-shot scaffold, not the interactive spec block
        self.assertNotIn("CPL_EXPAND_SPEC", out)
        self.assertIn("Task", out)
        self.assertIn("add caching", out)

    def test_non_interactive_config_renders_scaffold(self):
        cfg = {"use_model": False,
               "expand": {"interactive": False, "default_framework": "race"}}
        out = expand.run(Context(prompt="build a parser", args="build a parser",
                                 config=cfg, event="command")).payload
        self.assertNotIn("CPL_EXPAND_SPEC", out)
        self.assertIn("Role", out)            # race section label
        self.assertIn("build a parser", out)

    def test_short_q_flag_forces_scaffold(self):
        cfg = {"use_model": False,
               "expand": {"interactive": True, "default_framework": "default"}}
        out = expand.run(Context(prompt="-q add caching", args="-q add caching",
                                 config=cfg, event="command")).payload
        self.assertNotIn("CPL_EXPAND_SPEC", out)
        self.assertIn("add caching", out)

    def test_model_oneshot_uses_generate(self):
        cfg = {"use_model": True, "model": "x",
               "model_endpoint": "http://localhost:1/api", "model_timeout_ms": 1500,
               "expand": {"interactive": False, "default_framework": "default"}}
        with mock.patch("cpl.shared.model_client.generate",
                        return_value="Task: do the thing") as gen:
            out = expand.run(Context(prompt="do the thing", args="do the thing",
                                     config=cfg, event="command")).payload
        gen.assert_called_once()
        self.assertIn("do the thing", out)
        self.assertNotIn("CPL_EXPAND_SPEC", out)


if __name__ == "__main__":
    unittest.main()
