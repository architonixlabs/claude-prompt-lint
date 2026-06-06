#!/usr/bin/env python3
"""Eval harness (M3) — measure the gate's false-positive / false-negative rates.

Runs the gate over labelled prompt sets and reports:
  * False Positive Rate (FPR): good prompts wrongly flagged. KEEP THIS LOW —
    a gate that over-blocks gets disabled day one.
  * False Negative Rate (FNR): bad prompts that slip through.

Usage:
    python eval/run_eval.py
    python eval/run_eval.py --threshold-sweep
    python eval/run_eval.py --use-model        # also exercise Tier 2 (needs Ollama)

A "flag" = the gate would block (mode=block) or warn (mode=warn). For eval we
treat any non-pass action as a flag, independent of mode.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cpl.registry import Context  # noqa: E402
from cpl.shared import config as config_mod  # noqa: E402
from cpl.skills import gate  # noqa: E402

EVAL_DIR = _REPO_ROOT / "eval"


def _load_prompts(path: Path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def _is_flagged(prompt: str, cfg) -> tuple[bool, int]:
    """Return (flagged, score). Flagged = gate did not pass it."""
    ctx = Context(prompt=prompt, config=cfg, log_path=None, event="UserPromptSubmit")
    res = gate.run(ctx)
    return (res.action != "pass", res.score)


def _run(cfg, label_good, label_bad):
    good = _load_prompts(EVAL_DIR / "prompts_good.txt")
    bad = _load_prompts(EVAL_DIR / "prompts_bad.txt")

    good_flagged = [(p, *_is_flagged(p, cfg)) for p in good]
    bad_flagged = [(p, *_is_flagged(p, cfg)) for p in bad]

    fp = [(p, s) for (p, f, s) in good_flagged if f]      # good wrongly flagged
    fn = [(p, s) for (p, f, s) in bad_flagged if not f]   # bad that slipped through

    n_good = len(good) or 1
    n_bad = len(bad) or 1
    fpr = len(fp) / n_good * 100
    fnr = len(fn) / n_bad * 100

    print("=" * 64)
    print(f"cpl eval — {len(good)} good, {len(bad)} bad prompts")
    print(f"  use_model      : {cfg.get('use_model')}")
    print(f"  block_threshold: {cfg.get('block_threshold')}")
    print("-" * 64)
    print(f"  False Positive Rate (good flagged) : {fpr:5.1f}%  "
          f"({len(fp)}/{len(good)})")
    print(f"  False Negative Rate (bad passed)   : {fnr:5.1f}%  "
          f"({len(fn)}/{len(bad)})")
    print("-" * 64)

    if fp:
        print("  ⚠️  Good prompts wrongly flagged (lower this!):")
        for p, s in fp:
            print(f"    [score {s:3d}] {p[:70]}")
    else:
        print("  ✅ No good prompts flagged.")

    if fn:
        print(f"  ↪ Bad prompts that slipped through ({len(fn)}):")
        for p, s in fn[:8]:
            print(f"    [score {s:3d}] {p[:70]}")
        if len(fn) > 8:
            print(f"    … and {len(fn) - 8} more")
    print("=" * 64)
    return fpr, fnr


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-model", action="store_true",
                        help="exercise Tier 2 (requires Ollama running)")
    parser.add_argument("--threshold-sweep", action="store_true",
                        help="(reserved) sweep block_threshold values")
    ns = parser.parse_args(argv)

    cfg = config_mod.load_config()
    # For eval, force enabled and choose model usage explicitly.
    cfg["enabled"] = True
    cfg["use_model"] = bool(ns.use_model)

    _run(cfg, "good", "bad")
    return 0


if __name__ == "__main__":
    sys.exit(main())
