# Design: Project-context memory (`/cpl init`)

**Date:** 2026-06-21
**Status:** Approved (design), pending implementation plan
**Owner:** Ram Chandra Samal · Architonix Labs

## Summary

Add `/cpl init`: it generates a concise **project-context section inside the
project-root `CLAUDE.md`** so the AI has the project's stack, commands, layout,
and conventions every session — without re-deriving them. cpl deterministically
writes a factual baseline (no model), then the command asks Claude to enrich it
once. The section is delimited so hand-written `CLAUDE.md` content is preserved.

## Why this shape

Claude Code **already loads `CLAUDE.md` natively, once per session, at zero
per-turn token cost.** So the right design is *generation*, not injection: cpl
produces and maintains the context; the platform delivers it. This avoids the
per-prompt token cost of `additionalContext` injection entirely.

## Goals

- `/cpl init` scans the repo locally (no model) and writes/refreshes a
  cpl-managed section in the project-root `CLAUDE.md`.
- The command then instructs Claude to enrich that section (architecture,
  conventions) — a one-time cost. `--quick` skips enrichment (baseline only).
- **Merge-safe & idempotent:** cpl only touches text between its delimiters;
  re-running refreshes just that section and preserves everything else.
- **Zero per-turn cost:** relies on native `CLAUDE.md` loading; no hook, no
  per-prompt injection.

## Non-goals (YAGNI)

- No per-prompt context injection (the native `CLAUDE.md` path is cheaper).
- No file-watching / auto-refresh — refresh is `/cpl init` on demand.
- No global/user-level context; project-root `CLAUDE.md` only.
- No deep semantic code analysis in Python — facts are deterministic; depth
  comes from the optional Claude enrichment step.

## Components

### 1. `cpl/shared/project.py` (new) — deterministic scanner

`scan(root: str | Path) -> dict` returns a facts dict, fail-safe (any
sub-detector error is swallowed; returns whatever it gathered):

```python
{
  "name": "claude-prompt-lint",
  "languages": ["Python", "Markdown"],          # top few by file count
  "manifests": ["pyproject.toml"],              # detected manifest files
  "commands": {"install": "...", "test": "...", # inferred, omitted if unknown
               "build": "...", "run": "..."},
  "layout": ["cpl/", "hooks/", "eval/", "tests/", ...],   # top-level dirs
  "git": {"remote": "https://github.com/...", "branch": "main"},
  "entry_points": ["hooks/dispatcher.py"],
}
```

Detection rules (all stdlib, no shelling out):
- **name:** git remote basename (strip `.git`) → else `root` dir name.
- **languages:** walk the tree (skipping `_SKIP_DIRS`: `.git`, `node_modules`,
  `__pycache__`, `.venv`, `venv`, `dist`, `build`, `.mypy_cache`,
  `.pytest_cache`, `.idea`, `.vscode`), histogram file extensions, map common
  ones to language names, report the top 3–5. Capped at `_MAX_FILES` (e.g.
  4000) like `scope`.
- **manifests + commands:** detect and infer —
  - `package.json` → npm; read `scripts` for `build`/`test`/`start`; install
    `npm install`.
  - `pyproject.toml` / `requirements.txt` / `setup.py` → Python; install
    `pip install -r requirements.txt` (or `-e .`); test `pytest` if a
    `tests/`+pytest config, else `python -m unittest discover -s tests` when a
    `tests/` dir exists.
  - `Cargo.toml` → `cargo build` / `cargo test` / `cargo run`.
  - `go.mod` → `go build ./...` / `go test ./...`.
  - `Makefile` → note up to ~5 target names.
- **layout:** top-level directory names (skip hidden + `_SKIP_DIRS`), ~10 max.
- **git:** read `.git/HEAD` (`ref: refs/heads/<branch>`) and `.git/config`
  (`[remote "origin"] url`). No subprocess.
- **entry_points:** presence of common ones (`main.py`, `app.py`, `manage.py`,
  `src/main.*`, `index.js`, `hooks/dispatcher.py`, `cmd/`).

### 2. `cpl/skills/init.py` (new) — the `init` command

Command-only skill (`command="init"`, no hook). `run(ctx)`:
1. Parse a leading `--quick` flag.
2. `facts = project.scan(ctx.cwd)`.
3. Render the cpl section markdown from `facts` (`_render(facts)`).
4. Merge into the target file (`cfg["init"]["claude_md"]`, default `CLAUDE.md`,
   resolved against `ctx.cwd`) via `_merge_section`.
5. Return a `message`: a summary of what was written + the file path, and —
   unless `--quick` — an `ENRICH` instruction block the command layer (Claude)
   acts on to deepen the section.

Merge helper (pure, unit-tested):
```python
_START = "<!-- cpl:context:start -->"
_END = "<!-- cpl:context:end -->"

def _merge_section(existing: str, section: str) -> str:
    """Replace the delimited cpl section in `existing`, else append it."""
```
- Both markers present → replace the span (inclusive) with `section`.
- Markers absent, file non-empty → append `"\n\n" + section`.
- Empty/new file → `section`.
Idempotent: running twice yields exactly one cpl section.

Section shape:
```markdown
<!-- cpl:context:start -->
## Project context (maintained by `cpl` — run `/cpl init` to refresh)

**Project:** claude-prompt-lint
**Stack:** Python, Markdown
**Commands:** install `pip install -r requirements.txt` · test
`python -m unittest discover -s tests`
**Layout:** cpl/ · hooks/ · eval/ · tests/ · commands/
**Git:** github.com/architonixlabs/claude-prompt-lint (branch `main`)

<!-- cpl:enrich — architecture, conventions, gotchas go here -->
<!-- cpl:context:end -->
```
(Lines for unknown facts are omitted, not left blank.)

### 3. `commands/cpl.md` (modify)

Add an `/cpl init` row and a behaviour note: after the dispatcher writes the
baseline, if the output contains an `ENRICH` block (i.e. not `--quick`), Claude
should read the repo and rewrite the text **between the cpl markers** in
`CLAUDE.md` to add a short architecture/conventions/gotchas paragraph — concise,
since `CLAUDE.md` loads every session — without touching anything outside the
markers.

### 4. Config

```json
"init": { "claude_md": "CLAUDE.md" }
```
plus `"init": true` in the `skills` map (the single on/off; `claude_md` only
overrides the target filename). No redundant `enabled` flag.

## Data flow

```
/cpl init [--quick]
   │
   ├─ dispatcher → init skill (Python):
   │     facts = project.scan(cwd)
   │     write _render(facts) into CLAUDE.md cpl-section (merge-safe)
   │     return summary (+ ENRICH block unless --quick)
   │
   └─ command layer (Claude), if ENRICH present:
         read repo → rewrite text between cpl markers with concise
         architecture/conventions → done (never edits outside the markers)
```

## Error handling / fail-safe

- `scan` never raises; sub-detector failures are swallowed and that fact is
  omitted. An empty repo yields a minimal section (name + layout).
- Writing `CLAUDE.md`: if the file can't be written (permissions), the command
  returns a clear message and makes no partial write (write to a temp file then
  `os.replace`).
- `_merge_section` is pure and total; malformed/duplicate markers degrade to a
  single clean section (replace from first start to last end).

## Testing

Pure-stdlib `unittest`:
- `tests/test_project.py` — `scan` on a temp repo with a `package.json`
  (scripts → commands), a `pyproject.toml`, a `Cargo.toml`; language histogram;
  vendored-dir skipping; git remote/branch parsed from a fake `.git/config` +
  `.git/HEAD`; fail-safe on a missing/empty dir.
- `tests/test_init.py` — `_merge_section`: replace existing section, append when
  absent, create when no file, preserve surrounding content, idempotent (twice →
  one section), tolerate duplicate markers; the `init` command writes a
  `CLAUDE.md` in a temp cwd and returns a summary; `--quick` omits the ENRICH
  block; non-quick includes it.
- Existing gate eval (FPR 0%) and all current tests stay green.

## Backward compatibility

- New command-only skill; nothing runs on the hook, no change to the gate, mask,
  or other skills. Projects without `CLAUDE.md` get one created; projects with
  one keep all content outside the cpl markers.

## Build order (for the plan)

1. `project.py` scanner + `tests/test_project.py`.
2. `init.py` skill (`_merge_section`, `_render`, command) + registry + config +
   `tests/test_init.py`.
3. `commands/cpl.md` enrichment instructions.
4. Docs (README section + config row), CHANGELOG, version bump.
