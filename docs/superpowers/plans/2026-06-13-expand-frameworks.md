# Prompt Frameworks in `/cpl expand` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a data-driven prompt-framework library (AIM/RACE/COSTAR/TAG + default) to the `expand` skill, with an interactive picker + guided fill, personal defaults, and user-defined frameworks.

**Architecture:** Frameworks are declarative JSON files loaded from `frameworks/` (shipped) and `~/.cpl/frameworks/` (user override). A new `cpl/shared/frameworks.py` loads/resolves them. `expand` renders one-shot (static scaffold or local model) **or** emits a machine-readable spec the command layer (`commands/cpl.md`, i.e. Claude) uses to drive the interactive picker + guided fill. The headless gate hook is untouched and stays zero-token.

**Tech Stack:** Python 3 standard library only (no pip deps). Tests use stdlib `unittest`. Run from repo root.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `frameworks/default.json` … `tag.json` | The 5 shipped framework definitions | Create |
| `cpl/shared/frameworks.py` | Load/merge/resolve/list frameworks; `Framework` dataclass | Create |
| `cpl/skills/expand.py` | Arg parsing, mode selection, one-shot render, spec emit | Rewrite |
| `config/cpl.config.json` | New `expand` defaults block | Modify |
| `commands/cpl.md` | Interactive picker + guided-fill instructions | Modify |
| `tests/test_frameworks.py` | Library unit tests | Create |
| `tests/test_expand.py` | expand parsing/mode unit tests | Create |
| `README.md`, `CHANGELOG.md`, version files | Docs + release | Modify |

Branch: `feat/expand-frameworks` (already created; spec at `docs/superpowers/specs/2026-06-13-expand-frameworks-design.md`).

---

## Task 1: Framework library + seed definitions

**Files:**
- Create: `frameworks/default.json`, `frameworks/aim.json`, `frameworks/race.json`, `frameworks/costar.json`, `frameworks/tag.json`
- Create: `cpl/shared/frameworks.py`
- Test: `tests/test_frameworks.py`

- [ ] **Step 1: Create the 5 seed framework JSON files**

`frameworks/default.json`:
```json
{
  "name": "default",
  "aliases": ["tacd"],
  "description": "Task / Anchor / Constraints / Done-when — the default structure.",
  "sections": [
    {"label": "Task", "guidance": "the core ask in one line"},
    {"label": "Anchor", "guidance": "file/function/error to act on"},
    {"label": "Constraints", "guidance": "what to preserve / avoid"},
    {"label": "Done when", "guidance": "how success is verified"}
  ]
}
```

`frameworks/aim.json`:
```json
{
  "name": "aim",
  "aliases": [],
  "description": "Audience / Intent / Message — frame a request by who, why, what.",
  "sections": [
    {"label": "Audience", "guidance": "who the output is for"},
    {"label": "Intent", "guidance": "what you want to achieve"},
    {"label": "Message", "guidance": "the core content to convey or build"}
  ]
}
```

`frameworks/race.json`:
```json
{
  "name": "race",
  "aliases": [],
  "description": "Role / Action / Context / Expectation — a general task framework.",
  "sections": [
    {"label": "Role", "guidance": "who the assistant should act as"},
    {"label": "Action", "guidance": "the specific task to perform"},
    {"label": "Context", "guidance": "background, constraints, relevant files"},
    {"label": "Expectation", "guidance": "what a good result looks like"}
  ]
}
```

`frameworks/costar.json`:
```json
{
  "name": "costar",
  "aliases": [],
  "description": "Context / Objective / Style / Tone / Audience / Response.",
  "sections": [
    {"label": "Context", "guidance": "background the model needs"},
    {"label": "Objective", "guidance": "the precise goal"},
    {"label": "Style", "guidance": "writing or code style to follow"},
    {"label": "Tone", "guidance": "register, e.g. formal/terse"},
    {"label": "Audience", "guidance": "who consumes the result"},
    {"label": "Response", "guidance": "required output format"}
  ]
}
```

`frameworks/tag.json`:
```json
{
  "name": "tag",
  "aliases": [],
  "description": "Task / Action / Goal — a compact action framework.",
  "sections": [
    {"label": "Task", "guidance": "what needs doing"},
    {"label": "Action", "guidance": "the concrete steps to take"},
    {"label": "Goal", "guidance": "the end state you want"}
  ]
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_frameworks.py`:
```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m unittest tests.test_frameworks -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cpl.shared.frameworks'`

- [ ] **Step 4: Implement `cpl/shared/frameworks.py`**

```python
"""Prompt-framework library for the expand skill.

Frameworks are declarative JSON files: a name, aliases, a one-line description,
and an ordered list of sections (label + guidance). Loaded from the plugin's
frameworks/ dir and from ~/.cpl/frameworks/ (user files win on a name/alias
collision). Fully fail-safe — a missing dir or bad file is skipped.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Framework:
    name: str
    description: str
    sections: List[Dict[str, str]]            # [{"label":..., "guidance":...}]
    aliases: List[str] = field(default_factory=list)


# Hard-coded fallback so expand never breaks even if no files load.
_DEFAULT = Framework(
    name="default",
    description="Task / Anchor / Constraints / Done-when — the default structure.",
    sections=[
        {"label": "Task", "guidance": "the core ask in one line"},
        {"label": "Anchor", "guidance": "file/function/error to act on"},
        {"label": "Constraints", "guidance": "what to preserve / avoid"},
        {"label": "Done when", "guidance": "how success is verified"},
    ],
)


def _plugin_dir() -> Path:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        return Path(root) / "frameworks"
    return Path(__file__).resolve().parents[2] / "frameworks"


def _user_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".cpl" / "frameworks"


def _parse(path: Path) -> Optional[Framework]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", "")).strip()
    sections_in = data.get("sections")
    if not name or not isinstance(sections_in, list) or not sections_in:
        return None
    sections = []
    for s in sections_in:
        if isinstance(s, dict) and s.get("label"):
            sections.append({"label": str(s["label"]),
                             "guidance": str(s.get("guidance", ""))})
    if not sections:
        return None
    aliases = [str(a).lower() for a in data.get("aliases", []) if str(a).strip()]
    return Framework(name=name, description=str(data.get("description", "")),
                     sections=sections, aliases=aliases)


def load_frameworks() -> Dict[str, Framework]:
    """Map every name + alias (lowercased) to its Framework. User dir overrides."""
    out: Dict[str, Framework] = {}
    for d in (_plugin_dir(), _user_dir()):
        try:
            if not d.is_dir():
                continue
            files = sorted(d.glob("*.json"))
        except Exception:
            continue
        for fp in files:
            fw = _parse(fp)
            if fw is None:
                continue
            for key in [fw.name.lower(), *fw.aliases]:
                out[key] = fw
    out.setdefault("default", _DEFAULT)
    return out


def resolve(token: str, cfg: Dict) -> Tuple[Framework, bool]:
    """Resolve the first CLI token to a framework.

    Returns (framework, token_consumed). A token matching a known name/alias is
    consumed; otherwise the configured default_framework (fallback 'default') is
    returned and the token is left for the prompt.
    """
    frameworks = load_frameworks()
    key = (token or "").strip().lower()
    if key and key in frameworks:
        return frameworks[key], True
    exp = cfg.get("expand", {}) if isinstance(cfg, dict) else {}
    default_name = str(exp.get("default_framework", "default")).lower()
    fw = frameworks.get(default_name) or frameworks.get("default") or _DEFAULT
    return fw, False


def list_frameworks() -> List[Tuple[str, str]]:
    """Unique (name, description) pairs, sorted by name."""
    seen: Dict[str, str] = {}
    for fw in load_frameworks().values():
        seen[fw.name] = fw.description
    return sorted(seen.items())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m unittest tests.test_frameworks -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add frameworks/ cpl/shared/frameworks.py tests/test_frameworks.py
git commit -m "feat(frameworks): data-driven framework library + 5 seed frameworks"
```

---

## Task 2: Rewire `expand` onto the framework library

**Files:**
- Modify: `cpl/skills/expand.py` (full rewrite)
- Modify: `config/cpl.config.json` (add `expand` block)
- Test: `tests/test_expand.py`

- [ ] **Step 1: Add the `expand` config block**

In `config/cpl.config.json`, add this key (after `"debug_log": false,` and before `"skills"`):
```json
  "expand": {
    "default_framework": "default",
    "interactive": true,
    "tone": "neutral",
    "verbosity": "concise"
  },
```
Verify the file still parses: `python -c "import json; json.load(open('config/cpl.config.json'))"` → no output, exit 0.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_expand.py`:
```python
"""Tests for the expand skill's framework parsing and modes (stdlib unittest)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.registry import Context  # noqa: E402
from cpl.skills import expand  # noqa: E402


def _ctx(args, **cfg):
    base = {"use_model": False, "expand": {"interactive": True,
            "default_framework": "default", "tone": "neutral",
            "verbosity": "concise"}}
    base.update(cfg)
    return Context(prompt=args, args=args, config=base, event="command")


class Parsing(unittest.TestCase):
    def test_no_args_lists_frameworks(self):
        out = expand.run(_ctx("")).payload
        self.assertIn("available frameworks", out.lower())
        self.assertIn("race", out)

    def test_named_framework_is_consumed(self):
        # interactive spec should name RACE and carry the remaining prompt
        out = expand.run(_ctx("race fix the login bug")).payload
        self.assertIn("framework: race", out)
        self.assertIn("prompt: fix the login bug", out)

    def test_unknown_first_word_is_prompt(self):
        out = expand.run(_ctx("fix the race condition")).payload
        self.assertIn("framework: default", out)
        self.assertIn("prompt: fix the race condition", out)


class Modes(unittest.TestCase):
    def test_quick_flag_forces_static_scaffold(self):
        cfg = {"use_model": False,
               "expand": {"interactive": True, "default_framework": "default"}}
        out = expand.run(Context(prompt="--quick add caching",
                                 args="--quick add caching", config=cfg,
                                 event="command")).payload
        # one-shot scaffold, not the interactive spec block
        self.assertNotIn("CPL_EXPAND_SPEC", out)
        self.assertIn("Task", out)
        self.assertIn("add caching", out)

    def test_non_interactive_config_renders_scaffold(self):
        cfg = {"use_model": False,
               "expand": {"interactive": False, "default_framework": "race"}}
        out = expand.run(Context(prompt="build a parser", args="build a parser",
                                 config=cfg, event="command")).payload
        self.assertNotIn("CPL_EXPAND_SPEC", out)
        self.assertIn("Role", out)            # race section label
        self.assertIn("build a parser", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m unittest tests.test_expand -v`
Expected: FAIL (current expand.py has no framework parsing; `test_named_framework_is_consumed` fails on missing `framework: race`).

- [ ] **Step 4: Rewrite `cpl/skills/expand.py`**

```python
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
```

- [ ] **Step 5: Run the new + existing skill tests**

Run: `python -m unittest tests.test_expand tests.test_skills -v`
Expected: PASS. (Note: `tests/test_skills.py::test_all_command_skills_produce_output` runs `expand` with `args="add caching"` and a config lacking an `expand` block → `interactive` defaults to True → it returns the spec block, which is still a non-empty `message`. The assertion only checks `action=="message"` and non-empty payload, so it still passes.)

- [ ] **Step 6: Run the full suite + eval to confirm no regressions**

Run: `python -m unittest discover -s tests` then `python eval/run_eval.py`
Expected: all tests OK; eval FPR `0.0%`.

- [ ] **Step 7: Commit**

```bash
git add cpl/skills/expand.py config/cpl.config.json tests/test_expand.py
git commit -m "feat(expand): framework-aware modes (interactive spec / --quick one-shot)"
```

---

## Task 3: Interactive instructions in the command layer

**Files:**
- Modify: `commands/cpl.md`

This task has no automated test (it's Claude-facing prose). Verify by reading.

- [ ] **Step 1: Add an `expand` behaviour section to `commands/cpl.md`**

Append to the `## Behaviour notes` section of `commands/cpl.md`:
```markdown
### `/cpl expand` (interactive)

The dispatcher output for `expand` may be a `CPL_EXPAND_SPEC` block (lines:
`framework:`, `description:`, `tone:`, `verbosity:`, `prompt:`, a `sections:`
list of `- Label: guidance`, and an `available_frameworks:` list). When you see
it, DO NOT relay it verbatim — drive an interactive flow instead:

1. **Picker.** If `framework:` is `default` *and the user did not name a
   framework*, offer the `available_frameworks` list and let them choose. If they
   named one, skip the picker.
2. **Guided fill.** For each section in `sections:`, gather content with the
   user. Seed each section from anything already in `prompt:`; only ask about
   sections that aren't already covered. Respect `tone:` and `verbosity:`.
3. **Assemble.** Present the finished prompt as labelled lines for the user to
   copy. Never send it on their behalf.

If the user wants no conversation, tell them to use `/cpl expand --quick
[framework] <prompt>`, which the dispatcher renders directly (relay that
verbatim). Output that is NOT a `CPL_EXPAND_SPEC` block (a scaffold, a model
result, or the framework list) is already final — relay it verbatim.
```

- [ ] **Step 2: Update the `/cpl expand` row in the command table**

In `commands/cpl.md`, change the expand row to:
```markdown
| `/cpl expand [framework] <prompt>` | Restructure a prompt with a framework (default/aim/race/costar/tag, or your own). Interactive unless `--quick`. |
```

- [ ] **Step 3: Verify the dispatcher emits a spec end-to-end**

Run:
```bash
CLAUDE_PLUGIN_ROOT="$(pwd)" python3 hooks/dispatcher.py --command expand race fix the login bug
```
Expected: a `CPL_EXPAND_SPEC` block naming `framework: race` and `prompt: fix the login bug`.

- [ ] **Step 4: Commit**

```bash
git add commands/cpl.md
git commit -m "docs(command): interactive picker + guided fill for /cpl expand"
```

---

## Task 4: Docs, CHANGELOG, version bump

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `cpl/__init__.py`

- [ ] **Step 1: README — update the expand row + add a Frameworks subsection**

In `README.md`, change the `/cpl expand` table row to:
```markdown
| `/cpl expand [framework] <prompt>` | Restructure a prompt with a framework (interactive). |
```
Add this subsection after the `/cpl` commands table:
```markdown
### Prompt frameworks (`/cpl expand`)

`expand` structures a prompt using a named framework. Ships with `default`
(Task/Anchor/Constraints/Done-when), `aim` (Audience/Intent/Message), `race`,
`costar`, and `tag`. `/cpl expand` (no args) lists them.

- Apply one: `/cpl expand race fix the login bug`.
- Interactive by default — cpl walks you through each section. One-shot:
  `/cpl expand --quick race fix the login bug`.
- Personal defaults live under `"expand"` in `~/.cpl/config.json`
  (`default_framework`, `interactive`, `tone`, `verbosity`).
- **Your own frameworks:** drop a JSON file in `~/.cpl/frameworks/` — same shape
  as the shipped ones (`name`, `aliases`, `description`, `sections`). A file that
  reuses a shipped name overrides it.
```

- [ ] **Step 2: README — document the `expand` config block**

In the config table, add a row:
```markdown
| `expand` | (object) | `default_framework`, `interactive`, `tone`, `verbosity` for `/cpl expand`. |
```

- [ ] **Step 3: CHANGELOG entry**

Add at the top of `CHANGELOG.md` (under the title block, above `## [1.2.0]`):
```markdown
## [1.3.0] — 2026-06-13

### Added
- **Prompt frameworks for `/cpl expand`.** A data-driven library — `default`,
  `aim`, `race`, `costar`, `tag` — applied with `/cpl expand <framework>
  <prompt>`. `/cpl expand` lists them.
- **Interactive expand.** By default cpl runs a framework picker (when none is
  named) and a guided section fill, then assembles the prompt. `--quick` (or
  `"expand": {"interactive": false}`) keeps the one-shot render.
- **Personal defaults + custom frameworks.** An `"expand"` config block
  (`default_framework`, `interactive`, `tone`, `verbosity`) and user-defined
  frameworks in `~/.cpl/frameworks/*.json` (override shipped ones by name).

```

- [ ] **Step 4: Bump version to 1.3.0 in all three files**

```bash
python3 - <<'PY'
import json, re, pathlib
p=pathlib.Path(".claude-plugin/plugin.json"); d=json.loads(p.read_text(encoding="utf-8")); d["version"]="1.3.0"; p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
p=pathlib.Path(".claude-plugin/marketplace.json"); d=json.loads(p.read_text(encoding="utf-8")); d["metadata"]["version"]="1.3.0"; d["plugins"][0]["version"]="1.3.0"; p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
p=pathlib.Path("cpl/__init__.py"); t=p.read_text(encoding="utf-8"); p.write_text(re.sub(r'__version__ = "[^"]+"','__version__ = "1.3.0"',t),encoding="utf-8")
print("bumped to 1.3.0")
PY
```

- [ ] **Step 5: Final verification**

Run: `python -m unittest discover -s tests` and `python eval/run_eval.py`
Expected: all tests OK; eval FPR `0.0%`.
Then clean: `python -m compileall -q cpl hooks eval tests` → exit 0.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md .claude-plugin/ cpl/__init__.py
git commit -m "docs: frameworks docs + config; release v1.3.0"
```

---

## Task 5: Open PR

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin feat/expand-frameworks
gh pr create -R architonixlabs/claude-prompt-lint --base main --head feat/expand-frameworks \
  --title "Prompt frameworks for /cpl expand (v1.3.0)" \
  --body "Implements docs/superpowers/specs/2026-06-13-expand-frameworks-design.md. Data-driven framework library (default/aim/race/costar/tag), interactive picker + guided fill, personal defaults, and user frameworks in ~/.cpl/frameworks/. Backward compatible; gate untouched. Tests + eval green."
```

- [ ] **Step 2: Confirm CI passes**

Run: `gh pr checks <PR#> -R architonixlabs/claude-prompt-lint`
Expected: both `tests + eval` jobs pass.

---

## Self-Review (completed by plan author)

- **Spec coverage:** framework library (Task 1) · data format + 5 seeds (Task 1) ·
  config defaults (Task 2) · expand modes incl. `--quick` and one-shot (Task 2) ·
  interactive picker + guided fill (Task 3) · custom `~/.cpl/frameworks/` (Task 1
  loader + Task 4 docs) · backward compat (Task 2 tests) · testing (Tasks 1–2) ·
  docs + release (Task 4). All spec sections map to a task.
- **Placeholders:** none — every code/ test step contains complete code.
- **Type consistency:** `Framework(name, description, sections, aliases)`,
  `resolve()->(Framework,bool)`, `load_frameworks()->dict`, `list_frameworks()->
  list[(name,desc)]` used identically across tasks and tests.
- **Note:** the existing `tests/test_skills.py` expand smoke test still passes
  because the interactive spec block is a non-empty `message` (verified in Task 2,
  Step 5).
