"""Tests for the v1.6.0 repositioning behaviors (stdlib unittest):

  * gate warn-mode coaches the assistant by default, with a `note` opt-out
  * gate block-mode offers `/cpl rewrite`
  * `/cpl init` drift detection (new / up-to-date / refreshed), stable to its
    own CLAUDE.md write
  * `/cpl stats share` emits the single shareable hygiene line

These guard exactly the surfaces most likely to regress silently — the gate's
pass/flag decision is covered by eval/, so here we assert on *wording* and the
init/stats side effects.
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
from cpl.skills import gate, init as init_skill, stats as stats_skill  # noqa: E402

# Prompts with no concrete anchor that strong-fail Tier 1 (penalty >= 35),
# so they flag rules-only without needing the model.
_WEAK = "make the whole thing better and clean it all up everywhere ok thanks"
# A specific, anchored prompt the gate should pass.
_STRONG = "add a unit test for parseToken() in auth.py covering the expired-token case"


def _gate_ctx(prompt, **cfg):
    base = {"enabled": True, "use_model": False, "min_length_skip": 40}
    base.update(cfg)
    return Context(prompt=prompt, config=base, log_path=None,
                   event="UserPromptSubmit")


class GateFeedback(unittest.TestCase):
    def test_warn_coaches_the_assistant_by_default(self):
        res = gate.run(_gate_ctx(_WEAK, mode="warn"))
        self.assertEqual(res.action, "inject")
        self.assertIn("Note for the assistant", res.payload)
        self.assertNotIn("Prompt quality note", res.payload)

    def test_note_style_restores_the_classic_user_note(self):
        res = gate.run(_gate_ctx(_WEAK, mode="warn", feedback_style="note"))
        self.assertEqual(res.action, "inject")
        self.assertIn("Prompt quality note", res.payload)
        self.assertNotIn("Note for the assistant", res.payload)

    def test_block_offers_the_rewrite(self):
        res = gate.run(_gate_ctx(_WEAK, mode="block"))
        self.assertEqual(res.action, "block")
        self.assertIn("/cpl rewrite", res.payload)

    def test_anchored_prompt_passes(self):
        res = gate.run(_gate_ctx(_STRONG, mode="warn"))
        self.assertEqual(res.action, "pass")


class InitDrift(unittest.TestCase):
    def _status(self, payload):
        return next(l for l in payload.splitlines() if "Status" in l)

    def test_new_then_uptodate_then_drift_then_uptodate(self):
        d = Path(tempfile.mkdtemp())
        ctx = Context(prompt="", args="--quick", cwd=str(d), config={},
                      event="command")
        self.assertIn("first run", self._status(init_skill.run(ctx).payload))
        # Re-running on the unchanged repo must NOT report drift, even though
        # the first run wrote a CLAUDE.md (a Markdown file).
        self.assertIn("up to date", self._status(init_skill.run(ctx).payload))
        # A real structural change (new manifest) flips the fingerprint.
        (d / "package.json").write_text('{"scripts":{"test":"x"}}',
                                        encoding="utf-8")
        self.assertIn("refreshed", self._status(init_skill.run(ctx).payload))
        # And it settles again.
        self.assertIn("up to date", self._status(init_skill.run(ctx).payload))


class StatsShare(unittest.TestCase):
    def test_share_emits_only_the_shareable_line(self):
        d = Path(tempfile.mkdtemp())
        log = d / "log.jsonl"
        recs = ([{"event": "gate", "action": "pass", "tier": "tier1"}] * 7
                + [{"event": "gate", "action": "inject", "tier": "tier1",
                    "style": "coach"}] * 2
                + [{"event": "gate", "action": "block", "tier": "tier1"}] * 1)
        log.write_text("\n".join(json.dumps(r) for r in recs) + "\n",
                       encoding="utf-8")
        ctx = Context(prompt="", args="share", config={}, event="command",
                      log_path=log)
        out = stats_skill.run(ctx).payload
        self.assertIn("prompt hygiene", out)
        self.assertIn("via claude-prompt-lint", out)
        # share-only must be a single line, not the full report.
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_full_report_surfaces_coached_count(self):
        d = Path(tempfile.mkdtemp())
        log = d / "log.jsonl"
        recs = ([{"event": "gate", "action": "inject", "tier": "tier1",
                  "style": "coach"}] * 3
                + [{"event": "gate", "action": "inject", "tier": "tier1",
                    "style": "note"}] * 1)
        log.write_text("\n".join(json.dumps(r) for r in recs) + "\n",
                       encoding="utf-8")
        ctx = Context(prompt="", args="", config={}, event="command",
                      log_path=log)
        out = stats_skill.run(ctx).payload
        # 3 of the 4 warns coached the assistant.
        self.assertIn("coached the assistant: 3", out)


if __name__ == "__main__":
    unittest.main()
