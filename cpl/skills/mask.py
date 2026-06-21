"""mask skill — secret/PII detection on every prompt + /cpl mask command.

Auto-runs on the UserPromptSubmit hook (registered before `gate`): secrets BLOCK
the prompt (the platform can't redact in place, so the block message carries the
prompt already masked, ready to resend), PII WARNs. Also exposes `/cpl mask
<text>` to redact text on demand.

Independent of the gate's enabled/mode. Fail-open: any error → pass.
Logs detector kinds only, never a secret value.
"""

from __future__ import annotations

from typing import Any, Dict

from cpl.registry import Context, Result, Skill
from cpl.shared import feedback, log, secrets


def _mask_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    m = cfg.get("mask") if isinstance(cfg, dict) else None
    return m if isinstance(m, dict) else {}


def _log(ctx: Context, action: str, findings) -> None:
    if ctx.log_path is None:
        return
    log.append(ctx.log_path, {
        "event": "mask",
        "action": action,
        "kinds": sorted({f.kind for f in findings}),  # kinds only, never values
    })


def _run_command(ctx: Context) -> Result:
    text = (ctx.args or ctx.prompt or "").strip()
    if not text:
        return Result(action="message",
                      payload="[cpl mask] Usage: /cpl mask <text to redact>")
    findings = secrets.scan(text, ctx.config)
    if not findings:
        return Result(action="message",
                      payload="🔒 cpl mask — nothing sensitive detected.")
    masked = secrets.mask_text(text, findings)
    return Result(action="message",
                  payload="🔒 cpl mask — redacted (copy & paste):\n\n" + masked)


def run(ctx: Context) -> Result:
    cfg = ctx.config or {}

    # Command path: /cpl mask <text>
    if ctx.event == "command":
        return _run_command(ctx)

    # Hook path.
    mcfg = _mask_cfg(cfg)
    if not mcfg.get("enabled", True):
        return Result(action="pass", meta={"skill": "mask", "reason": "disabled"})

    findings = secrets.scan(ctx.prompt, cfg)
    if not findings:
        return Result(action="pass", meta={"skill": "mask"})

    # Secrets → block (unless block_secrets is off, then they warn).
    if secrets.has_block(findings) and mcfg.get("block_secrets", True):
        masked = secrets.mask_text(ctx.prompt, findings)
        payload = feedback.format_mask_block(findings, masked)
        _log(ctx, "block", findings)
        return Result(action="block", payload=payload, meta={"skill": "mask"})

    # PII (or downgraded secrets) → warn.
    if mcfg.get("warn_pii", True) and (secrets.has_warn(findings)
                                       or secrets.has_block(findings)):
        payload = feedback.format_mask_warn(findings)
        _log(ctx, "inject", findings)
        return Result(action="inject", payload=payload, meta={"skill": "mask"})

    _log(ctx, "pass", findings)
    return Result(action="pass", meta={"skill": "mask"})


SKILL = Skill(name="mask", run=run, hook="UserPromptSubmit", command="mask")
