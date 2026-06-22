"""Tests for the /cpl audit readout (stdlib unittest).

Asserts it surfaces mask + guard catches, summarizes by source/kind, and never
needs (or shows) a secret value — it reads only the metadata log.
"""
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

from cpl.registry import Context  # noqa: E402
from cpl.skills import audit  # noqa: E402


def _log_with(records, d):
    p = d / "log.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return p


class Audit(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def _ctx(self, log_path, args=""):
        return Context(prompt="", args=args, config={}, event="command",
                       log_path=log_path)

    def test_no_log_is_graceful(self):
        out = audit.run(self._ctx(self.d / "missing.jsonl")).payload
        self.assertIn("No log", out)

    def test_clean_log_reports_nothing_caught(self):
        log = _log_with([{"event": "gate", "action": "pass", "tier": "tier1"}], self.d)
        out = audit.run(self._ctx(log)).payload
        self.assertIn("no secrets caught", out.lower())

    def test_summarizes_mask_and_guard_catches(self):
        recs = [
            {"event": "mask", "action": "block", "kinds": ["private_key"],
             "ts": "2026-06-22T01:00:00+00:00"},
            {"event": "guard", "action": "deny", "tool": "read",
             "kinds": "connection_string", "ts": "2026-06-22T01:05:00+00:00"},
            {"event": "guard", "action": "warn", "tool": "write",
             "kinds": ["aws"], "ts": "2026-06-22T01:06:00+00:00"},
            {"event": "gate", "action": "inject", "tier": "tier1"},  # not security
        ]
        out = audit.run(self._ctx(_log_with(recs, self.d))).payload
        self.assertIn("Total catches : 3", out)
        self.assertIn("prompt-mask 1", out)
        self.assertIn("tool-guard 2", out)
        self.assertIn("private_key", out)
        # never leaks a value — the log only had kinds, so the output can't either
        self.assertNotIn("BEGIN", out)


if __name__ == "__main__":
    unittest.main()
