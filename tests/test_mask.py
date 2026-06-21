"""Tests for the mask skill (hook + command) — stdlib unittest."""
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
from cpl.skills import mask  # noqa: E402

_SECRET = "deploy with AKIAIOSFODNN7EXAMPLE to prod and restart the worker"
_PII = "email the report to jane.doe@example.com after the run finishes"


def _cfg(**over):
    base = {"mask": {"enabled": True, "block_secrets": True, "warn_pii": True,
                     "allowlist": [], "custom_patterns": []}}
    base.update(over)
    return base


def _hook(prompt, cfg):
    return mask.run(Context(prompt=prompt, config=cfg, event="UserPromptSubmit"))


class HookPath(unittest.TestCase):
    def test_secret_blocks(self):
        res = _hook(_SECRET, _cfg())
        self.assertEqual(res.action, "block")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", res.payload)  # never echo raw
        self.assertIn("cleaned version", res.payload.lower())

    def test_pii_warns(self):
        res = _hook(_PII, _cfg())
        self.assertEqual(res.action, "inject")

    def test_clean_passes(self):
        res = _hook("refactor parseToken() in auth.py and add a test", _cfg())
        self.assertEqual(res.action, "pass")

    def test_block_secrets_false_downgrades(self):
        res = _hook(_SECRET, _cfg(mask={"enabled": True, "block_secrets": False,
                                        "warn_pii": True}))
        self.assertEqual(res.action, "inject")   # warn, not block

    def test_disabled_passes(self):
        res = _hook(_SECRET, _cfg(mask={"enabled": False}))
        self.assertEqual(res.action, "pass")

    def test_bypass_prefix_still_blocks_secret(self):
        res = _hook("!! " + _SECRET, _cfg())
        self.assertEqual(res.action, "block")

    def test_log_records_kinds_not_values(self):
        p = Path(tempfile.mktemp(suffix=".jsonl"))
        try:
            mask.run(Context(prompt=_SECRET, config=_cfg(), log_path=p,
                             event="UserPromptSubmit"))
            body = p.read_text(encoding="utf-8") if p.exists() else ""
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", body)
            if body:
                self.assertIn("aws_access_key", body)
        finally:
            if p.exists():
                p.unlink()


class CommandPath(unittest.TestCase):
    def test_mask_command_redacts(self):
        res = mask.run(Context(prompt="", args=_SECRET, config=_cfg(),
                               event="command"))
        self.assertEqual(res.action, "message")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", res.payload)

    def test_mask_command_clean_text(self):
        res = mask.run(Context(prompt="", args="nothing secret here at all",
                               config=_cfg(), event="command"))
        self.assertEqual(res.action, "message")


if __name__ == "__main__":
    unittest.main()
