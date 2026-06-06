"""Tier 1 rule library — instant, deterministic, no model.

Each rule inspects the prompt and may contribute to a soft *penalty* score
(0 = perfect, higher = weaker) plus human-readable issues and suggestions.

The dispatcher maps the penalty to a verdict:
  - very low penalty  -> strong PASS  (skip the model entirely)
  - very high penalty -> strong FAIL  (block/warn now, skip the model)
  - middle            -> INCONCLUSIVE (escalate to Tier 2 model, if enabled)

Rules are intentionally lenient (low false-positive bias). A gate that
over-blocks gets disabled on day one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# --- Signal patterns -------------------------------------------------------

# Concrete anchors: things that make a prompt actionable.
_PATH_RE = re.compile(
    r"""(?x)
    (?:[\w./\\\-]+/[\w.\-]+)            # a/b/c style path
    | (?:[\w\-]+\.[A-Za-z]{1,6}\b)      # file.ext
    | (?:[A-Za-z]:[\\/][\w.\\/\- ]+)    # windows drive path
    """
)
_SYMBOL_RE = re.compile(
    r"""(?x)
    \b\w+\([^)]*\)                       # func() call
    | \b[A-Za-z_]\w*\.[A-Za-z_]\w+       # obj.method / module.attr
    | \b[A-Z][a-z0-9]+[A-Z]\w*           # CamelCase identifier
    | \b[a-z]+_[a-z_]+\b                 # snake_case identifier
    """
)
_BACKTICK_RE = re.compile(r"`[^`]+`")
_QUOTED_RE = re.compile(r"""(['\"]).+?\1""")
_ERROR_RE = re.compile(
    r"\b(error|exception|traceback|stack ?trace|failed|undefined|null|nan|"
    r"errno|segfault|panic|warning|stderr)\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+")
_NUMBER_RE = re.compile(r"\b\d{2,}\b")

# A digit tied to a unit/noun is a concrete constraint ("8 characters",
# "5 attempts", "200 status", "15 minutes", "480px").
_NUM_WITH_UNIT_RE = re.compile(
    r"\b\d+\s*"
    r"(characters?|chars?|attempts?|times?|seconds?|secs?|minutes?|mins?|"
    r"hours?|days?|items?|rows?|columns?|bytes?|kb|mb|gb|px|%|ms|"
    r"status|code|port|page|pages|requests?|retries|retr(y|ies))\b",
    re.IGNORECASE,
)

# Well-known fixed filenames (no extension) and routes/CLI tools that act as
# concrete anchors even though they don't match the path/symbol patterns.
_KNOWN_ANCHOR_RE = re.compile(
    r"\b(dockerfile|makefile|procfile|gemfile|rakefile|vagrantfile|jenkinsfile|"
    r"\.gitignore|\.env|readme|license|npm|yarn|pnpm|pip|cargo|gradle|maven|"
    r"git|curl|grep|sed|awk|ssh|kubectl|docker|webpack|babel|eslint|pytest|"
    r"mypy|jest|vitest)\b",
    re.IGNORECASE,
)

# Routes / endpoints like /login, /api/users, /healthz.
_ROUTE_RE = re.compile(r"(?<!\w)/[a-zA-Z][\w\-]*(?:/[\w\-{}:]+)*")

# A single literal char in quotes or backticks ("@", '+') is a concrete target.
_LITERAL_CHAR_RE = re.compile(r"""(['\"`]).['\"`]?\1?|(?<=\s)[@#&%/+]=?(?=\s)""")

# Dangling references with no concrete object: "fix it", "make this better".
_DANGLING_RE = re.compile(
    r"\b(fix|change|update|improve|refactor|clean ?up|optimi[sz]e|rewrite|"
    r"redo|handle|address|resolve|tweak|adjust|sort out)\s+"
    r"(it|this|that|these|those|them|things?|stuff|the code|everything)\b",
    re.IGNORECASE,
)

# Pure vague verb with no nearby object.
_VAGUE_VERB_RE = re.compile(
    r"\b(improve|optimi[sz]e|clean ?up|refactor|fix|enhance|polish|simplify|"
    r"modernize|streamline|tidy)\b",
    re.IGNORECASE,
)

# Acceptance-criteria / constraint signals (their absence is a soft penalty).
_CRITERIA_RE = re.compile(
    r"\b(should|must|expect|expected|so that|such that|ensure|return[s]?|"
    r"output|result|test|verify|assert|given|when|then|acceptance|"
    r"constraint|requirement|spec|until|without|don'?t|do not|avoid)\b",
    re.IGNORECASE,
)

# Build/change intent — prompts that ask for code work.
_BUILD_INTENT_RE = re.compile(
    r"\b(add|build|create|implement|write|make|fix|refactor|change|update|"
    r"modify|remove|delete|rename|migrate|convert|generate|handle|improve|"
    r"optimi[sz]e|clean ?up|enhance|polish|simplify|modernize|redo|rewrite|"
    r"sort out|look into|address|resolve|tweak|adjust|review)\b",
    re.IGNORECASE,
)

# Informational questions ("how does X work?", "what is Y?") are not change
# requests — we shouldn't push acceptance-criteria feedback at them.
_QUESTION_RE = re.compile(
    r"^\s*(how|what|why|when|where|who|which|can|could|would|should|is|are|"
    r"does|do|did|will|explain|describe|tell me)\b",
    re.IGNORECASE,
)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


@dataclass
class RuleResult:
    penalty: int = 0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    anchors: int = 0  # count of concrete anchors found (informational)
    categories: List[str] = field(default_factory=list)  # stable issue tags

    def add(
        self, penalty: int, issue: str, suggestion: str, category: str = ""
    ) -> None:
        self.penalty += penalty
        self.issues.append(issue)
        if suggestion:
            self.suggestions.append(suggestion)
        if category:
            self.categories.append(category)


def count_anchors(text: str) -> int:
    """How many concrete, actionable referents the prompt contains."""
    anchors = 0
    anchors += len(_BACKTICK_RE.findall(text))
    anchors += len(_PATH_RE.findall(text))
    anchors += len(_SYMBOL_RE.findall(text))
    anchors += len(_QUOTED_RE.findall(text))
    anchors += len(_ERROR_RE.findall(text))
    anchors += len(_URL_RE.findall(text))
    anchors += len(_NUMBER_RE.findall(text))
    anchors += len(_NUM_WITH_UNIT_RE.findall(text))
    anchors += len(_KNOWN_ANCHOR_RE.findall(text))
    anchors += len(_ROUTE_RE.findall(text))
    anchors += len(_LITERAL_CHAR_RE.findall(text))
    return anchors


def evaluate(text: str) -> RuleResult:
    """Run all Tier 1 rules and return an aggregate RuleResult."""
    res = RuleResult()
    stripped = text.strip()
    words = _word_count(stripped)
    res.anchors = count_anchors(stripped)
    has_intent = bool(_BUILD_INTENT_RE.search(stripped))
    is_question = bool(_QUESTION_RE.match(stripped))

    # Rule: dangling pronoun with a change verb and no anchor.
    if _DANGLING_RE.search(stripped) and res.anchors == 0:
        res.add(
            40,
            "Dangling reference: it's not clear what 'it/this/that' points to.",
            "Name the file, function, or symbol you mean "
            "(e.g. `fix the null check in auth.py:parseToken`).",
            category="dangling_reference",
        )

    # Rule: no concrete anchor at all in a substantive non-question prompt.
    # The strongest single signal: every well-specified engineering prompt
    # points at *something* (a path, symbol, error, quote, number, url).
    # Questions asking for information are exempt — they need no anchor.
    if res.anchors == 0 and words >= 6 and not is_question:
        res.add(
            35,
            "No concrete anchor: no file path, symbol, error text, or quoted target.",
            "Point at something specific — a path, a function name, the error message, "
            "or paste the relevant snippet.",
            category="no_anchor",
        )

    # Rule: pure vague verb with almost no object (very short + vague).
    if _VAGUE_VERB_RE.search(stripped) and words <= 5 and res.anchors == 0:
        res.add(
            20,
            "Vague verb with no object (e.g. 'improve', 'optimize', 'clean up').",
            "Say what to improve and what 'better' means here "
            "(faster? smaller? more readable? which metric?).",
            category="vague_verb",
        )

    # Soft signal: change request with no acceptance criteria / constraints.
    # A prompt already rich in concrete anchors (a named file + symbol, an
    # error, a quoted target) is actionable enough on its own — we don't push
    # an acceptance-criteria nag at it, and crucially we keep it out of the
    # model's inconclusive band where small models tend to over-flag.
    if has_intent and not _CRITERIA_RE.search(stripped) and res.anchors < 2:
        res.add(
            10,
            "No acceptance criteria: nothing states what 'done' looks like.",
            "Add what success looks like — expected output, a test that should pass, "
            "or constraints to respect.",
            category="no_acceptance_criteria",
        )

    # Soft signal: long ramble with no clear anchor (lots of words, no referents).
    if words >= 60 and res.anchors == 0:
        res.add(
            10,
            "Long prompt with no concrete anchor — the core ask may be buried.",
            "Lead with the one-line ask, then context. Reference the specific target.",
            category="long_ramble",
        )

    return res
