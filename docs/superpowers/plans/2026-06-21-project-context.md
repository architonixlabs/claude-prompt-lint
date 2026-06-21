# Project-Context Memory (`/cpl init`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/cpl init` scans the repo and writes a concise, cpl-managed project-context section into the project-root `CLAUDE.md` (which Claude Code loads natively each session), then asks Claude to enrich it.

**Architecture:** A new `cpl/shared/project.py` deterministically gathers facts (stack, commands, layout, git). A new command-only `cpl/skills/init.py` renders those facts into a delimited section and merge-writes it into `CLAUDE.md`, returning a summary plus (unless `--quick`) an enrichment instruction for the command layer. No hook, so zero per-turn token cost.

**Tech Stack:** Python 3 standard library only (no pip deps). Tests use stdlib `unittest`, run from repo root with `python3`.

## Global Constraints

- **Zero dependencies.** Standard library only. No third-party imports.
- **Fail-open / fail-safe.** `project.scan` never raises (returns partial facts); the `init` command never raises (reports a clear message on FS errors). Write `CLAUDE.md` atomically (temp file + `os.replace`); never leave a partial file.
- **Merge-safe.** cpl only edits text between `<!-- cpl:context:start -->` and `<!-- cpl:context:end -->`; all other `CLAUDE.md` content is preserved. Idempotent: running twice yields exactly one cpl section.
- **snake_case**, module docstrings explain "why". Commits: conventional prefix + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- Tests are stdlib `unittest` (`python3 -m unittest discover -s tests`); the gate eval (`python3 eval/run_eval.py`) must stay at **FPR 0.0%**.
- Spec: `docs/superpowers/specs/2026-06-21-project-context-design.md`. Branch: `feat/project-context`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `cpl/shared/project.py` | Deterministic repo scanner → facts dict | Create |
| `cpl/skills/init.py` | `init` command: render + merge-write CLAUDE.md | Create |
| `cpl/registry.py` | Add `"init"` to `_SKILL_MODULES` | Modify |
| `config/cpl.config.json` | `init` block + `"init": true` in skills | Modify |
| `commands/cpl.md`, `README.md`, `CHANGELOG.md`, version files | Docs + release | Modify |
| `tests/test_project.py`, `tests/test_init.py` | Unit tests | Create |

---

## Task 1: Deterministic repo scanner (`project.py`)

**Files:**
- Create: `cpl/shared/project.py`
- Test: `tests/test_project.py`

**Interfaces:**
- Produces: `scan(root) -> dict` with keys `name:str`, `languages:list[str]`, `manifests:list[str]`, `commands:dict[str,str]`, `layout:list[str]`, `git:dict` (`remote`,`branch` — may be absent), `entry_points:list[str]`. Never raises.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_project.py`:
```python
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
        # Nonexistent path → minimal dict, no raise.
        res = project.scan(Path(tempfile.gettempdir()) / "definitely_missing_xyz")
        self.assertIsInstance(res, dict)
        self.assertIn("name", res)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_project -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cpl.shared.project'`

- [ ] **Step 3: Implement `cpl/shared/project.py`**

```python
"""Deterministic project scanner for the `init` skill.

Gathers facts about a repo — name, languages, build/test commands, layout, git —
using only the standard library and only by reading files (no subprocess). Fully
fail-safe: any sub-detector error is swallowed and that fact is omitted, so
`scan` always returns a dict and never raises.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
              "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
              ".github"}
_MAX_FILES = 4000

_LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".rb": "Ruby", ".c": "C", ".h": "C", ".cpp": "C++",
    ".cs": "C#", ".php": "PHP", ".sh": "Shell", ".sql": "SQL",
    ".md": "Markdown", ".css": "CSS", ".html": "HTML", ".vue": "Vue",
    ".svelte": "Svelte", ".kt": "Kotlin", ".swift": "Swift",
}


def _languages(root: Path) -> List[str]:
    counts: Counter = Counter()
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if seen >= _MAX_FILES:
                break
            seen += 1
            lang = _LANG_BY_EXT.get(Path(fn).suffix.lower())
            if lang:
                counts[lang] += 1
    return [lang for lang, _ in counts.most_common(5)]


def _commands(root: Path, manifests: List[str]) -> Dict[str, str]:
    cmds: Dict[str, str] = {}
    if "package.json" in manifests:
        cmds["install"] = "npm install"
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
        except Exception:
            scripts = {}
        if "test" in scripts:
            cmds["test"] = "npm test"
        if "build" in scripts:
            cmds["build"] = "npm run build"
        if "start" in scripts:
            cmds["run"] = "npm start"
    if {"pyproject.toml", "requirements.txt", "setup.py"} & set(manifests):
        if "requirements.txt" in manifests:
            cmds.setdefault("install", "pip install -r requirements.txt")
        else:
            cmds.setdefault("install", "pip install -e .")
        if (root / "tests").is_dir():
            cmds.setdefault("test", "python -m unittest discover -s tests")
    if "Cargo.toml" in manifests:
        cmds.setdefault("install", "cargo build")
        cmds.setdefault("test", "cargo test")
        cmds.setdefault("run", "cargo run")
    if "go.mod" in manifests:
        cmds.setdefault("test", "go test ./...")
        cmds.setdefault("build", "go build ./...")
    return cmds


def _manifests(root: Path) -> List[str]:
    names = ["package.json", "pyproject.toml", "requirements.txt", "setup.py",
             "Cargo.toml", "go.mod", "Makefile", "pom.xml", "build.gradle"]
    return [n for n in names if (root / n).is_file()]


def _layout(root: Path) -> List[str]:
    out = []
    try:
        for p in sorted(root.iterdir()):
            if p.is_dir() and p.name not in _SKIP_DIRS and not p.name.startswith("."):
                out.append(p.name + "/")
    except Exception:
        return out
    return out[:10]


def _git(root: Path) -> Dict[str, str]:
    git: Dict[str, str] = {}
    head = root / ".git" / "HEAD"
    cfg = root / ".git" / "config"
    try:
        if head.is_file():
            m = re.match(r"ref:\s*refs/heads/(.+)", head.read_text(encoding="utf-8").strip())
            if m:
                git["branch"] = m.group(1).strip()
    except Exception:
        pass
    try:
        if cfg.is_file():
            m = re.search(r"\[remote \"origin\"\][^\[]*?url\s*=\s*(\S+)",
                          cfg.read_text(encoding="utf-8"))
            if m:
                url = m.group(1)
                url = re.sub(r"^https?://", "", url)
                url = re.sub(r"^git@([^:]+):", r"\1/", url)
                url = re.sub(r"\.git$", "", url)
                git["remote"] = url
    except Exception:
        pass
    return git


def _entry_points(root: Path) -> List[str]:
    candidates = ["main.py", "app.py", "manage.py", "src/main.py", "index.js",
                  "src/index.js", "src/main.ts", "hooks/dispatcher.py", "cmd"]
    return [c for c in candidates if (root / c).exists()]


def scan(root) -> Dict[str, Any]:
    """Return a facts dict about the repo. Never raises."""
    try:
        root = Path(root)
        name = root.name or "project"
        facts: Dict[str, Any] = {"name": name}
        try:
            facts["manifests"] = _manifests(root)
        except Exception:
            facts["manifests"] = []
        for key, fn in (("languages", lambda: _languages(root)),
                        ("layout", lambda: _layout(root)),
                        ("git", lambda: _git(root)),
                        ("entry_points", lambda: _entry_points(root))):
            try:
                facts[key] = fn()
            except Exception:
                facts[key] = [] if key != "git" else {}
        try:
            facts["commands"] = _commands(root, facts.get("manifests", []))
        except Exception:
            facts["commands"] = {}
        # Prefer git-remote basename for the name when available.
        remote = facts.get("git", {}).get("remote", "")
        if remote:
            facts["name"] = remote.rstrip("/").split("/")[-1] or name
        return facts
    except Exception:
        return {"name": "project", "languages": [], "manifests": [],
                "commands": {}, "layout": [], "git": {}, "entry_points": []}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_project -v`
Expected: PASS (all). Also run `python3 -m unittest discover -s tests` and `python3 eval/run_eval.py` → all OK, FPR 0.0%.

- [ ] **Step 5: Commit**

```bash
git add cpl/shared/project.py tests/test_project.py
git commit -m "feat(project): deterministic repo scanner (stack/commands/layout/git)"
```

---

## Task 2: The `init` command (render + merge-write CLAUDE.md)

**Files:**
- Create: `cpl/skills/init.py`
- Modify: `cpl/registry.py`, `config/cpl.config.json`
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: `project.scan(root) -> dict`; `Context` (fields `args`, `cwd`, `config`), `Result(action, payload, meta)`, `Skill`.
- Produces: `SKILL = Skill(name="init", run=run, command="init")`; module helpers `_merge_section(existing, section)`, `_render(facts)`.

- [ ] **Step 1: Add the `init` config block**

In `config/cpl.config.json`, add after the `"mask"` block and before `"skills"`:
```json
  "init": {
    "claude_md": "CLAUDE.md"
  },
```
And add `"init": true,` inside the `"skills"` object (e.g. after `"mask": true,`).
Verify: `python3 -c "import json; json.load(open('config/cpl.config.json'))"` → exit 0.

- [ ] **Step 2: Register the skill**

In `cpl/registry.py`, add `"init"` to `_SKILL_MODULES` (order only affects display for command skills; put it after `"template"`):
```python
_SKILL_MODULES = [
    "mask",
    "gate",
    "rewrite",
    "stats",
    "explain",
    "profile",
    "expand",
    "scope",
    "template",
    "init",
]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_init.py`:
```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_init -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cpl.skills.init'`

- [ ] **Step 5: Implement `cpl/skills/init.py`**

```python
"""init skill — /cpl init [--quick]

Writes a concise, cpl-managed project-context section into the project-root
CLAUDE.md (which Claude Code loads natively every session — zero per-turn token
cost). cpl fills a deterministic factual baseline; unless --quick, the command
layer (Claude) then enriches the section in place.

Merge-safe: only the text between the cpl markers is touched. Idempotent.
Fail-safe: reports a clear message on a write error; never raises.
"""

from __future__ import annotations

import os
from pathlib import Path

from cpl.registry import Context, Result, Skill
from cpl.shared import project

_START = "<!-- cpl:context:start -->"
_END = "<!-- cpl:context:end -->"


def _merge_section(existing: str, section: str) -> str:
    """Replace the delimited cpl section in `existing`, else append it.

    Tolerates duplicate markers by replacing from the first start to the last
    end. Pure and total."""
    if not existing.strip():
        return section
    i = existing.find(_START)
    if i == -1:
        return existing.rstrip() + "\n\n" + section + "\n"
    j = existing.rfind(_END)
    if j == -1 or j < i:
        return existing.rstrip() + "\n\n" + section + "\n"
    return existing[:i] + section + existing[j + len(_END):]


def _render(facts) -> str:
    lines = [_START,
             "## Project context (maintained by `cpl` — run `/cpl init` to refresh)",
             ""]
    lines.append(f"**Project:** {facts.get('name', 'project')}")
    langs = facts.get("languages") or []
    if langs:
        lines.append(f"**Stack:** {', '.join(langs)}")
    cmds = facts.get("commands") or {}
    if cmds:
        parts = [f"{k} `{v}`" for k, v in cmds.items()]
        lines.append("**Commands:** " + " · ".join(parts))
    layout = facts.get("layout") or []
    if layout:
        lines.append(f"**Layout:** {' · '.join(layout)}")
    git = facts.get("git") or {}
    if git.get("remote"):
        branch = f" (branch `{git['branch']}`)" if git.get("branch") else ""
        lines.append(f"**Git:** {git['remote']}{branch}")
    eps = facts.get("entry_points") or []
    if eps:
        lines.append(f"**Entry points:** {', '.join(eps)}")
    lines += ["",
              "<!-- cpl:enrich — architecture, conventions, gotchas go here -->",
              _END]
    return "\n".join(lines)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".cpltmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run(ctx: Context) -> Result:
    if ctx.event != "command":
        return Result(action="pass")

    args = (ctx.args or "").strip()
    quick = False
    if args.split()[:1] == ["--quick"]:
        quick = True

    cfg = ctx.config or {}
    init_cfg = cfg.get("init", {}) if isinstance(cfg.get("init"), dict) else {}
    fname = init_cfg.get("claude_md", "CLAUDE.md") or "CLAUDE.md"

    root = Path(ctx.cwd or os.getcwd())
    target = root / fname

    facts = project.scan(root)
    section = _render(facts)

    try:
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        merged = _merge_section(existing, section)
        _write_atomic(target, merged)
    except Exception:
        return Result(action="message",
                      payload=f"[cpl init] Could not write {target}. "
                              f"Check permissions and try again.")

    lines = ["🧭 cpl init",
             "",
             f"  Wrote project context to {fname} (cpl-managed section).",
             f"  Project: {facts.get('name', '?')} · "
             f"Stack: {', '.join(facts.get('languages') or []) or 'n/a'}",
             ""]
    if quick:
        lines.append("  Baseline written. Re-run `/cpl init` (no --quick) to let "
                     "cpl enrich it with architecture notes.")
    else:
        lines += [
            "ENRICH: Now read this repo and improve the section between the "
            f"`{_START}` and `{_END}` markers in {fname}: add a short, concise "
            "architecture / conventions / gotchas note (a few lines — this file "
            "loads every session). Edit ONLY the text between those markers; "
            "leave the factual lines and everything outside the markers intact."]
    return Result(action="message", payload="\n".join(lines),
                  meta={"skill": "init", "quick": quick})


SKILL = Skill(name="init", run=run, command="init")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_init -v`
Expected: PASS (all).

- [ ] **Step 7: Full suite + eval + end-to-end check**

Run:
```bash
python3 -m unittest discover -s tests
python3 eval/run_eval.py
CLAUDE_PLUGIN_ROOT="$(pwd)" python3 hooks/dispatcher.py --command init --quick
```
Expected: all tests OK; FPR 0.0%; the dispatcher prints the `🧭 cpl init` summary and a cpl section is now present in this repo's `CLAUDE.md`. **Then restore the repo's CLAUDE.md if it was changed:** `git checkout -- CLAUDE.md 2>/dev/null || rm -f CLAUDE.md` (don't commit a generated CLAUDE.md as part of this task — the repo may not want one; if `git status` shows CLAUDE.md modified/created, revert it).

- [ ] **Step 8: Commit**

```bash
git add cpl/skills/init.py cpl/registry.py config/cpl.config.json tests/test_init.py
git commit -m "feat(init): /cpl init writes a cpl-managed CLAUDE.md context section"
```

---

## Task 3: Command instructions, docs, version bump

**Files:**
- Modify: `commands/cpl.md`, `README.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `cpl/__init__.py`

- [ ] **Step 1: `commands/cpl.md` — add the init row + behaviour note**

Add a row to the command table:
```markdown
| `/cpl init [--quick]` | Generate/refresh a project-context section in `CLAUDE.md` (then I enrich it, unless `--quick`). |
```
Add under `## Behaviour notes`:
```markdown
### `/cpl init`

The dispatcher writes a deterministic factual baseline into a cpl-managed
section of `CLAUDE.md` and prints a summary. If that output contains an `ENRICH:`
line (i.e. the user did not pass `--quick`), read the repo and rewrite ONLY the
text between the `<!-- cpl:context:start -->` and `<!-- cpl:context:end -->`
markers to add a short architecture / conventions / gotchas note — concise,
since `CLAUDE.md` loads every session. Never touch anything outside the markers.
```

- [ ] **Step 2: `README.md` — add a section + config row**

After the "Data masking" subsection, add:
```markdown
### Project context (`/cpl init`)

`/cpl init` writes a concise project summary (stack, build/test commands, layout,
git) into a cpl-managed section of your project's `CLAUDE.md` — the file Claude
Code loads natively every session, so the AI knows your project without
re-deriving it, at **zero per-turn token cost**.

- cpl fills a deterministic baseline; then it enriches the section with
  architecture/convention notes. `/cpl init --quick` writes the baseline only.
- It only edits between its `<!-- cpl:context:start/end -->` markers — your own
  `CLAUDE.md` content is preserved. Re-run any time to refresh.
```
Add to the config table:
```markdown
| `init` | (object) | `claude_md` — the file `/cpl init` writes to (default `CLAUDE.md`). |
```

- [ ] **Step 3: CHANGELOG — add the 1.5.0 entry**

At the top of `CHANGELOG.md` (above `## [1.4.0]`):
```markdown
## [1.5.0] — 2026-06-21

### Added
- **Project context (`/cpl init`).** Scans the repo (stack, build/test commands,
  layout, git) and writes a concise, cpl-managed section into the project-root
  `CLAUDE.md` — which Claude Code loads natively each session, so the AI has
  project context without re-deriving it and at zero per-turn token cost. cpl
  fills a deterministic baseline, then enriches it; `--quick` writes baseline
  only. Only the text between the cpl markers is touched — your `CLAUDE.md`
  content is preserved.

```

- [ ] **Step 4: Bump version to 1.5.0**

```bash
python3 - <<'PY'
import json, re, pathlib
p=pathlib.Path(".claude-plugin/plugin.json"); d=json.loads(p.read_text(encoding="utf-8")); d["version"]="1.5.0"; p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
p=pathlib.Path(".claude-plugin/marketplace.json"); d=json.loads(p.read_text(encoding="utf-8")); d["metadata"]["version"]="1.5.0"; d["plugins"][0]["version"]="1.5.0"; p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
p=pathlib.Path("cpl/__init__.py"); t=p.read_text(encoding="utf-8"); p.write_text(re.sub(r'__version__ = "[^"]+"','__version__ = "1.5.0"',t),encoding="utf-8")
print("bumped to 1.5.0")
PY
```
Verify no mojibake / valid JSON:
`python3 -c "import json;[json.load(open(f,encoding='utf-8')) for f in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json']];print('ok')"`

- [ ] **Step 5: Final verification**

Run: `python3 -m unittest discover -s tests` ; `python3 eval/run_eval.py` ; `python3 -m compileall -q cpl hooks eval tests`
Expected: all OK; FPR 0.0%; compile exit 0. Confirm `git status` does not show a stray generated `CLAUDE.md` (revert if so).

- [ ] **Step 6: Commit**

```bash
git add commands/cpl.md README.md CHANGELOG.md .claude-plugin/ cpl/__init__.py
git commit -m "docs: project-context docs + config; release v1.5.0"
```

---

## Task 4: Open PR

- [ ] **Step 1: Push and open PR**

```bash
git push -u origin feat/project-context
gh pr create -R architonixlabs/claude-prompt-lint --base main --head feat/project-context \
  --title "Project context — /cpl init writes CLAUDE.md (v1.5.0)" \
  --body "Implements docs/superpowers/specs/2026-06-21-project-context-design.md. /cpl init scans the repo and writes a cpl-managed section into CLAUDE.md (native, zero per-turn cost), then enriches it. Merge-safe, idempotent, fail-safe. Tests + eval green."
```

- [ ] **Step 2: Confirm CI**

Run: `gh pr checks <PR#> -R architonixlabs/claude-prompt-lint`
Expected: both `tests + eval` jobs pass.

---

## Self-Review (completed by plan author)

- **Spec coverage:** scanner facts incl. git/commands/layout (Task 1) · `_merge_section` + `_render` + atomic write + `--quick` (Task 2) · registry + config (Task 2) · command enrichment instructions (Task 3) · docs/config/release (Task 3) · fail-safe (Task 1 `scan`, Task 2 write try/except) · merge-safe/idempotent (Task 2 tests). All spec sections map to a task.
- **Placeholders:** none — every code/test step has complete code.
- **Type consistency:** `scan(root)->dict`, `_merge_section(existing, section)->str`, `_render(facts)->str`, `Skill(name="init", run, command="init")` used identically across tasks and tests.
- **Guard:** Task 2 Step 7 and Task 3 Step 5 both remind the implementer NOT to commit a generated `CLAUDE.md` for this repo (the feature writes one when run, but the repo shouldn't ship a generated context file from a test run).
