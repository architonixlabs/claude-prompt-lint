"""Tests for the prompt-framework library (stdlib unittest)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.shared import frameworks as fw  # noqa: E402


class LoadAndResolve(unittest.TestCase):
    def test_ships_five_frameworks(self):
        names = {n for n, _ in fw.list_frameworks()}
        self.assertTrue({"default", "aim", "race", "costar", "tag"} <= names)

    def test_alias_resolves(self):
        loaded = fw.load_frameworks()
        self.assertIn("tacd", loaded)             # default's alias
        self.assertEqual(loaded["tacd"].name, "default")

    def test_resolve_consumes_known_token(self):
        f, consumed = fw.resolve("race", {})
        self.assertTrue(consumed)
        self.assertEqual(f.name, "race")

    def test_resolve_leaves_unknown_token(self):
        f, consumed = fw.resolve("fix", {})
        self.assertFalse(consumed)
        self.assertEqual(f.name, "default")

    def test_resolve_honors_config_default(self):
        f, consumed = fw.resolve("fix", {"expand": {"default_framework": "tag"}})
        self.assertFalse(consumed)
        self.assertEqual(f.name, "tag")


class UserOverrideAndSafety(unittest.TestCase):
    def test_malformed_file_is_skipped(self):
        # A bad JSON file in the plugin dir must not break loading.
        bad = _ROOT / "frameworks" / "_bad_tmp.json"
        bad.write_text("{not json", encoding="utf-8")
        try:
            names = {n for n, _ in fw.list_frameworks()}
            self.assertIn("default", names)       # still loads the good ones
        finally:
            bad.unlink()

    def test_default_always_present(self):
        self.assertIn("default", fw.load_frameworks())


if __name__ == "__main__":
    unittest.main()
