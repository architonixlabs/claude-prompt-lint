"""gate skill — block/warn weak prompts before they're sent.

Tiered evaluation (see Part C.1 of the build plan):

  Tier 0  escape hatches            -> PASS instantly
  Tier 1  local heuristic rules     -> strong PASS / strong FAIL / inconclusive
  Tier 2  local model (optional)    -> nuanced verdict for inconclusive cases

Sacred rules:
  * FAIL-OPEN — any error, or model down, results in PASS.
  * Lenient by default — low false-positive bias.
"""

from __future__ import annotations

from typing import Any, Dict

from cpl.registry import Context, Result, Skill
from cpl.shared import feedback, log, model_client, rules

# Tier 1 penalty bands (out of ~100). Tuned in M3 against the eval set.
# At these bands the rules-only gate scores ~0% FPR / ~7% FNR on eval/.
_STRONG_PASS_MAX = 9     # penalty <= this -> pass without the model
_STRONG_FAIL_MIN = 35    # penalty >= this -> act without the model


def _is_escape(prompt: str, cfg: Dict[str, Any]) -> bool:
    """Tier 0: things we never gate."""
    stripped = prompt.strip()
    if not stripped:
        return True
    bypass = cfg.get("bypass_prefix", "!!")
    if bypass and stripped.startswith(bypass):
        return True
    # Slash commands and shell escapes are not natural-language prompts.
    if stripped.startswith("/") or stripped.startswith("!"):
        return True
    if len(stripped) < int(cfg.get("min_length_skip", 40)):
        return True
    return False


def _verdict_to_result(
    cfg: Dict[str, Any],
    score: int,
    issues,
    suggestions,
    tier: str,
) -> Result:
    """Build a Result for a failing prompt according to mode."""
    mode = cfg.get("mode", "warn")
    bypass = cfg.get("bypass_prefix", "!!")

    if mode == "block":
        payload = feedback.format_block(
            score, issues, suggestions, bypass_prefix=bypass, mode="block"
        )
        return Result(
            action="block",
            payload=payload,
            score=score,
            issues=list(issues),
            suggestions=list(suggestions),
            meta={"tier": tier, "mode": mode},
        )

    # warn mode: inject a short note, prompt still proceeds.
    payload = feedback.format_warn_inject(score, issues, suggestions)
    return Result(
        action="inject",
        payload=payload,
        score=score,
        issues=list(issues),
        suggestions=list(suggestions),
        meta={"tier": tier, "mode": mode},
    )


def _log(ctx: Context, action: str, score: int, tier: str, issues) -> None:
    if ctx.log_path is None:
        return
    log.append(
        ctx.log_path,
        {
            "event": "gate",
            "action": action,
            "score": score,
            "tier": tier,
            "mode": ctx.config.get("mode", "warn"),
            "prompt_len": len(ctx.prompt.strip()),
            "issue_count": len(issues),
        },
    )


def run(ctx: Context) -> Result:
    cfg = ctx.config
    prompt = ctx.prompt

    if not cfg.get("enabled", True):
        return Result(action="pass", meta={"reason": "disabled"})

    # Tier 0 — escape hatches.
    if _is_escape(prompt, cfg):
        _log(ctx, "pass", 0, "tier0", [])
        return Result(action="pass", meta={"tier": "tier0"})

    # Tier 1 — local heuristic rules.
    try:
        r1 = rules.evaluate(prompt)
    except Exception:
        # Fail-open: a rule bug must never block the user.
        return Result(action="pass", meta={"tier": "tier1", "error": True})

    score = min(100, r1.penalty)

    # Strong pass — confident enough to skip the model.
    if r1.penalty <= _STRONG_PASS_MAX:
        _log(ctx, "pass", score, "tier1", r1.issues)
        return Result(action="pass", score=score, meta={"tier": "tier1"})

    # Strong fail — confident enough to act without the model.
    if r1.penalty >= _STRONG_FAIL_MIN:
        res = _verdict_to_result(cfg, score, r1.issues, r1.suggestions, "tier1")
        _log(ctx, res.action, score, "tier1", r1.issues)
        return res

    # Inconclusive — escalate to Tier 2 model if enabled.
    if cfg.get("use_model", False):
        verdict = model_client.evaluate(
            prompt,
            endpoint=cfg.get("model_endpoint"),
            model=cfg.get("model"),
            timeout_ms=int(cfg.get("model_timeout_ms", 1500)),
        )
        if verdict is not None:
            # Merge: take the higher (more cautious) of rule vs model score,
            # but defer to the model's pass/fail decision on its own threshold.
            m_score = int(verdict.get("score", 0))
            merged_score = max(score, m_score)
            threshold = int(cfg.get("block_threshold", 50))
            if (not verdict.get("pass", True)) or merged_score >= threshold:
                issues = (r1.issues + verdict.get("issues", []))
                suggestions = (r1.suggestions + verdict.get("suggestions", []))
                res = _verdict_to_result(
                    cfg, merged_score, issues, suggestions, "tier2"
                )
                _log(ctx, res.action, merged_score, "tier2", issues)
                return res
            _log(ctx, "pass", merged_score, "tier2", r1.issues)
            return Result(action="pass", score=merged_score, meta={"tier": "tier2"})
        # Model down / malformed -> fail-open to pass (don't punish ambiguity).
        _log(ctx, "pass", score, "tier2-failopen", r1.issues)
        return Result(action="pass", score=score, meta={"tier": "tier2-failopen"})

    # Model disabled and only middling penalty -> lenient pass.
    _log(ctx, "pass", score, "tier1-lenient", r1.issues)
    return Result(action="pass", score=score, meta={"tier": "tier1-lenient"})


SKILL = Skill(name="gate", run=run, hook="UserPromptSubmit")
