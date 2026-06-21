"""Tests for the deterministic project scanner (stdlib unittest)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cpl.shared import project  # noqa: E402


class Scan(unittest.TestCase):
    def _repo(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    def test_name_from_dir(self):
        d = self._repo()
        (d / "a.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(project.scan(d)["name"], d.name)

    def test_languages_histogram(self):
        d = self._repo()
        (d / "a.py").write_text("x=1\n", encoding="utf-8")
        (d / "b.py").write_text("y=2\n", encoding="utf-8")
        (d / "c.md").write_text("# hi\n", encoding="utf-8")
        langs = project.scan(d)["languages"]
        self.assertEqual(langs[0], "Python")          # most files
        self.assertIn("Markdown", langs)

    def test_python_commands(self):
        d = self._repo()
        (d / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (d / "tests").mkdir()
        cmds = project.scan(d)["commands"]
        self.assertIn("unittest", cmds.get("test", "") + cmds.get("install", ""))

    def test_npm_commands_from_scripts(self):
        d = self._repo()
        (d / "package.json").write_text(
            '{"scripts":{"test":"jest","build":"webpack"}}', encoding="utf-8")
        cmds = project.scan(d)["commands"]
        self.assertEqual(cmds["test"], "npm test")
        self.assertEqual(cmds["build"], "npm run build")
        self.assertEqual(cmds["install"], "npm install")

    def test_cargo_commands(self):
        d = self._repo()
        (d / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
        cmds = project.scan(d)["commands"]
        self.assertEqual(cmds["test"], "cargo test")

    def test_layout_skips_vendored(self):
        d = self._repo()
        (d / "src").mkdir()
        (d / "node_modules").mkdir()
        (d / ".git").mkdir()
        layout = project.scan(d)["layout"]
        self.assertIn("src/", layout)
        self.assertNotIn("node_modules/", layout)
        self.assertNotIn(".git/", layout)

    def test_git_parsed_from_files(self):
        d = self._repo()
        g = d / ".git"
        g.mkdir()
        (g / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (g / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/o/r.git\n',
            encoding="utf-8")
        git = project.scan(d)["git"]
        self.assertEqual(git["branch"], "main")
        self.assertIn("github.com/o/r", git["remote"])

    def test_failsafe_on_missing_dir(self):
        # Nonexistent path -> minimal dict, no raise.
        res = project.scan(Path(tempfile.gettempdir()) / "definitely_missing_xyz")
        self.assertIsInstance(res, dict)
        self.assertIn("name", res)


if __name__ == "__main__":
    unittest.main()
