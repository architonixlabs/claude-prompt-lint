"""expand skill — /cpl expand [framework] [prompt]

Applies a prompt framework (default / aim / race / costar / tag, or your own in
~/.cpl/frameworks/) to a terse prompt.

Modes:
  * interactive (default): emit a CPL_EXPAND_SPEC block the command layer
    (Claude) uses to run a picker + guided section fill.
  * one-shot (--quick, or expand.interactive=false): render here — model-applied
    when the local model is on, else a static fill-in scaffold.

Backward compatible: `/cpl expand fix the login bug` uses the default framework.
"""

from __future__ import annotations

from cpl.registry import Context, Result, Skill
from cpl.shared import frameworks as fwlib
from cpl.shared import model_client

_EXPAND_TIMEOUT_MS = 8000


def _split_quick(args: str):
    toks = args.split()
    if toks and toks[0] in ("--quick", "-q"):
        return " ".join(toks[1:]).strip(), True
    return args, False


def _split_framework(args: str, cfg):
    toks = args.split(maxsplit=1)
    first = toks[0] if toks else ""
    fw, consumed = fwlib.resolve(first, cfg)
    if consumed:
        prompt = toks[1].strip() if len(toks) > 1 else ""
    else:
        prompt = args.strip()
    return fw, prompt


def _static_scaffold(fw, prompt) -> str:
    lines = ["🧱 cpl expand", "", f"  Framework : {fw.name}", ""]
    if prompt:
        lines += [f"  Original  : {prompt}", ""]
    lines += ["  Fill the brackets, then send:", ""]
    width = max(len(s["label"]) for s in fw.sections)
    for s in fw.sections:
        lines.append(f"    {s['label'].ljust(width)} : [{s['guidance']}]")
    return "\n".join(lines)


def _model_system(fw, tone, verbosity) -> str:
    labels = "\n".join(f"{s['label']}: <{s['guidance']}>" for s in fw.sections)
    return (
        f"You restructure a software-engineering prompt using the {fw.name} "
        f"framework. Output exactly these labelled lines, filling in what the "
        f"user gave and leaving a short [bracketed placeholder] for anything they "
        f"did not specify. Do NOT invent specifics. Tone: {tone}; verbosity: "
        f"{verbosity}. Format:\n{labels}\nReturn only those lines."
    )


def _framework_spec(fw, prompt, tone, verbosity) -> str:
    lines = ["CPL_EXPAND_SPEC",
             f"framework: {fw.name}",
             f"description: {fw.description}",
             f"tone: {tone}",
             f"verbosity: {verbosity}",
             f"prompt: {prompt}",
             "sections:"]
    for s in fw.sections:
        lines.append(f"  - {s['label']}: {s['guidance']}")
    lines.append("available_frameworks:")
    for name, desc in fwlib.list_frameworks():
        lines.append(f"  - {name}: {desc}")
    return "\n".join(lines)


def _list_message() -> str:
    lines = ["🧱 cpl expand — available frameworks", "",
             "  Usage: /cpl expand [framework] <your prompt>", ""]
    for name, desc in fwlib.list_frameworks():
        lines.append(f"    {name:<10} {desc}")
    lines += ["", "  Add your own: drop a JSON file in ~/.cpl/frameworks/"]
    return "\n".join(lines)


def run(ctx: Context) -> Result:
    cfg = ctx.config or {}
    exp = cfg.get("expand", {}) if isinstance(cfg.get("expand"), dict) else {}
    tone = exp.get("tone", "neutral")
    verbosity = exp.get("verbosity", "concise")
    interactive = bool(exp.get("interactive", True))

    raw = (ctx.args or ctx.prompt or "").strip()
    raw, quick = _split_quick(raw)

    if not raw:
        return Result(action="message", payload=_list_message())

    fw, prompt = _split_framework(raw, cfg)

    # Interactive (default): emit the spec for the command layer to drive.
    if interactive and not quick:
        return Result(action="message",
                      payload=_framework_spec(fw, prompt, tone, verbosity),
                      meta={"mode": "interactive", "framework": fw.name})

    # One-shot, model-applied when on and a prompt is present.
    if cfg.get("use_model", False) and prompt:
        timeout = max(int(cfg.get("model_timeout_ms", 1500)), _EXPAND_TIMEOUT_MS)
        full = (f"{_model_system(fw, tone, verbosity)}\n\n"
                f"TERSE PROMPT:\n<<<\n{prompt}\n>>>\n\nSTRUCTURED PROMPT:")
        out = model_client.generate(full, endpoint=cfg.get("model_endpoint"),
                                     model=cfg.get("model"), timeout_ms=timeout)
        if out:
            body = ["🧱 cpl expand", "", f"  Framework : {fw.name}", "",
                    f"  Original  : {prompt}", "",
                    "  Structured (fill any [placeholders]):", ""]
            for ln in out.splitlines():
                body.append(f"    {ln}")
            return Result(action="message", payload="\n".join(body),
                          meta={"mode": "model", "framework": fw.name})

    # One-shot static scaffold (model off / unavailable).
    return Result(action="message", payload=_static_scaffold(fw, prompt),
                  meta={"mode": "scaffold", "framework": fw.name})


SKILL = Skill(name="expand", run=run, command="expand")
