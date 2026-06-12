"""Regression guards for the gate's core invariant and the fixed issues.

Pure stdlib (unittest). Run from the repo root:
    python -m unittest discover -s tests
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
from cpl.skills import gate, scope, stats  # noqa: E402
from cpl.shared import log  # noqa: E402


def _load(name):
    out = []
    for line in (_ROOT / "eval" / name).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


class GateFalsePositiveRate(unittest.TestCase):
    """The sacred invariant: rules-only gate flags ZERO good prompts."""

    def test_zero_false_positives_on_good_set(self):
        cfg = {"enabled": True, "mode": "warn", "use_model": False,
               "bypass_prefix": "!!", "min_length_skip": 40,
               "block_threshold": 50}
        flagged = []
        for p in _load("prompts_good.txt"):
            res = gate.run(Context(prompt=p, config=cfg, event="UserPromptSubmit"))
            if res.action != "pass":
                flagged.append(p)
        self.assertEqual(flagged, [], f"{len(flagged)} good prompts wrongly flagged")


class Issue1StatsCountsWarns(unittest.TestCase):
    def test_warn_only_log_reports_nonzero_tokens(self):
        p = Path(tempfile.mktemp(suffix=".jsonl"))
        recs = [{"event": "gate", "action": "inject", "tier": "tier1"}] * 4
        p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        try:
            out = stats.run(Context(prompt="", config={}, log_path=p,
                                    event="command")).payload
            line = [ln for ln in out.splitlines() if "tokens saved" in ln][0]
            num = int(line.split("~")[1].split()[0].replace(",", ""))
            self.assertGreater(num, 0, "warn-mode tokens-saved must not be 0")
        finally:
            p.unlink()


class Issue2ScopeWordBoundary(unittest.TestCase):
    def test_partial_symbol_not_falsely_found(self):
        d = Path(tempfile.mkdtemp())
        (d / "x.py").write_text("def evaluate_all():\n    pass\n", encoding="utf-8")
        try:
            found = scope._symbols_present(d, ["evaluate()"])
            self.assertNotIn("evaluate()", found)  # must not match evaluate_all
        finally:
            import shutil
            shutil.rmtree(d)

    def test_prose_snake_case_not_extracted(self):
        syms = scope._SYMBOL_RE.findall("add the sign_in flow and log_out button")
        self.assertNotIn("sign_in", syms)
        self.assertNotIn("log_out", syms)


class Issue4LogBounding(unittest.TestCase):
    def test_tail_returns_last_n_in_order(self):
        p = Path(tempfile.mktemp(suffix=".jsonl"))
        try:
            for i in range(50):
                log.append(p, {"event": "gate", "i": i})
            t = log.tail(p, 5)
            self.assertEqual([r["i"] for r in t], [45, 46, 47, 48, 49])
        finally:
            p.unlink()

    def test_trim_bounds_file(self):
        p = Path(tempfile.mktemp(suffix=".jsonl"))
        old_max, old_keep = log._MAX_BYTES, log._KEEP_RECORDS
        log._MAX_BYTES, log._KEEP_RECORDS = 500, 20
        try:
            for i in range(200):
                log.append(p, {"event": "gate", "i": i})
            recs = log.read_all(p)
            self.assertLessEqual(len(recs), 21)
            self.assertEqual(recs[-1]["i"], 199)
        finally:
            log._MAX_BYTES, log._KEEP_RECORDS = old_max, old_keep
            p.unlink()


if __name__ == "__main__":
    unittest.main()
