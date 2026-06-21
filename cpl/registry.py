"""Skill registry — the extensibility core.

Every capability is a Skill implementing a tiny common interface. The
dispatcher asks the registry to resolve a trigger (a hook event or a `/cpl
<command>`) to a skill, then runs it.

Adding a skill = add a module under cpl/skills/ exposing `SKILL`, then list
it in `_SKILL_MODULES` below. No dispatcher changes. That is the whole point.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# --- Skill interface -------------------------------------------------------

# Action vocabulary the dispatcher knows how to act on:
#   "pass"    -> let the prompt proceed (empty stdout)
#   "block"   -> erase prompt, show payload to user (decision:block)
#   "message" -> print payload to user (command output)
#   "inject"  -> append payload to context (warn mode / enrich)
ACTIONS = ("pass", "block", "message", "inject")


@dataclass
class Context:
    """Everything a skill needs to do its job."""
    prompt: str                       # the user's prompt (hook) or command args
    args: str = ""                    # raw args for /cpl <skill> <args>
    cwd: str = ""                     # repo / working dir
    config: Dict[str, Any] = field(default_factory=dict)
    log_path: Optional[Path] = None
    event: str = ""                   # "UserPromptSubmit" or "command"


@dataclass
class Result:
    action: str = "pass"              # one of ACTIONS
    payload: str = ""                 # text for block/message/inject
    score: int = 0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Skill:
    name: str
    run: Callable[[Context], Result]
    hook: Optional[str] = None        # hook event this skill handles, if any
    command: Optional[str] = None     # /cpl <command> token, if any


# --- Discovery -------------------------------------------------------------

# Order matters only for display; resolution is by trigger match.
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
]


class Registry:
    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._by_command: Dict[str, Skill] = {}
        self._by_hook: Dict[str, List[Skill]] = {}
        self._all: List[Skill] = []
        self._load()

    def _enabled(self, name: str) -> bool:
        skills_cfg = self._config.get("skills", {})
        # Default to enabled if the skill isn't listed.
        return bool(skills_cfg.get(name, True))

    def _load(self) -> None:
        for mod_name in _SKILL_MODULES:
            if not self._enabled(mod_name):
                continue
            try:
                mod = importlib.import_module(f"cpl.skills.{mod_name}")
            except Exception:
                continue
            skill = getattr(mod, "SKILL", None)
            if not isinstance(skill, Skill):
                continue
            self._all.append(skill)
            if skill.command:
                self._by_command[skill.command] = skill
            if skill.hook:
                self._by_hook.setdefault(skill.hook, []).append(skill)

    def for_hook(self, event: str) -> List[Skill]:
        return list(self._by_hook.get(event, []))

    def for_command(self, command: str) -> Optional[Skill]:
        return self._by_command.get(command)

    def commands(self) -> List[str]:
        return sorted(self._by_command.keys())

    def all(self) -> List[Skill]:
        return list(self._all)
