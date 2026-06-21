"""Tests for the init skill (render + merge-write CLAUDE.md). Stdlib unittest."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cpl.registry import Context  # noqa: E402
from cpl.skills import init  # noqa: E402

_START = "<!-- cpl:context:start -->"
_END = "<!-- cpl:context:end -->"


class MergeSection(unittest.TestCase):
    def test_append_when_absent(self):
        out = init._merge_section("# My notes\n", f"{_START}\nX\n{_END}")
        self.assertIn("# My notes", out)
        self.assertIn(f"{_START}\nX\n{_END}", out)

    def test_replace_existing(self):
        existing = f"# Top\n\n{_START}\nOLD\n{_END}\n\n# Bottom\n"
        out = init._merge_section(existing, f"{_START}\nNEW\n{_END}")
        self.assertIn("# Top", out)
        self.assertIn("# Bottom", out)
        self.assertIn("NEW", out)
        self.assertNotIn("OLD", out)

    def test_idempotent_single_section(self):
        sec = f"{_START}\nX\n{_END}"
        once = init._merge_section("", sec)
        twice = init._merge_section(once, sec)
        self.assertEqual(once.count(_START), 1)
        self.assertEqual(twice.count(_START), 1)

    def test_empty_existing_is_section(self):
        sec = f"{_START}\nX\n{_END}"
        self.assertEqual(init._merge_section("", sec), sec)


class RunCommand(unittest.TestCase):
    def _cwd(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        (d / "a.py").write_text("x=1\n", encoding="utf-8")
        return d

    def _ctx(self, d, args=""):
        return Context(prompt=args, args=args, cwd=str(d),
                       config={"init": {"claude_md": "CLAUDE.md"}}, event="command")

    def test_writes_claude_md_and_section(self):
        d = self._cwd()
        res = init.run(self._ctx(d))
        self.assertEqual(res.action, "message")
        text = (d / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(_START, text)
        self.assertIn(_END, text)
        self.assertIn("Project context", text)

    def test_preserves_existing_content(self):
        d = self._cwd()
        (d / "CLAUDE.md").write_text("# Keep me\n", encoding="utf-8")
        init.run(self._ctx(d))
        text = (d / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("# Keep me", text)
        self.assertIn(_START, text)

    def test_quick_omits_enrichment(self):
        d = self._cwd()
        res = init.run(self._ctx(d, args="--quick"))
        self.assertNotIn("ENRICH", res.payload)

    def test_non_quick_includes_enrichment(self):
        d = self._cwd()
        res = init.run(self._ctx(d))
        self.assertIn("ENRICH", res.payload)

    def test_write_error_reports_message(self):
        d = self._cwd()
        # Make the target a directory so write_text fails.
        (d / "CLAUDE.md").mkdir()
        res = init.run(self._ctx(d))
        self.assertEqual(res.action, "message")
        self.assertIn("Could not write", res.payload)


if __name__ == "__main__":
    unittest.main()
