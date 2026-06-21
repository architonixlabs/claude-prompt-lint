# cpl Popularity — Intent

**Problem statement.** claude-prompt-lint (cpl) is well-engineered but mis-positioned. Its adoption gap is a positioning and distribution problem, not a code-quality one. cpl leads with its weakest, most-annoying job (a prompt-quality gate) and buries its strongest felt jobs (secret-leak prevention, project-context freshness), while fighting the platform trend instead of riding it. The fix is to change how the engine *responds* and which *segment* it serves — not to rebuild it.

## Core diagnosis (why it isn't catching on)

- **Small pain, felt by a minority.** The hero promise ("save clarification tokens") only lands for API-metered users; Max/Pro subscribers feel no per-token cost, and a clarification round-trip is cheap and fast — not painful enough to install a gate against.
- **Invisible when it works.** A linter that correctly passes ~95% of prompts produces silence — no aha-moment, no dopamine, no visible win.
- **Caught between lenient and annoying.** Lenient default = invisible = no value; stricter = nags power users who disable it within a day (the README itself admits this fear).
- **Friction is inverse to value.** The strong tier (local model) needs Ollama + a 2GB pull + serve + config edit; the zero-config path is the weak rules tier.
- **Fights the platform trend.** Claude Code keeps getting better at planning and asking good clarifying questions, so the marginal value of pre-linting a human prompt shrinks over time.
- **Ten surfaces, no hero.** gate/rewrite/expand/explain/scope/profile/stats/template/mask/init reads as a feature checklist, not one indispensable job. The "lint" metaphor also overpromises ESLint-grade determinism that subjective, model-judged prompt quality can't deliver.

## Refined thesis (post-adversarial)

Keep the gate **ENGINE** — the local prompt eval at 0% false-positive rate is the differentiated IP. The gate's mistake was never its existence; it was its **response modality**. Change it:

- **Scold → offer-a-fix / coach Claude.** Stop judging the user. Either offer an accept-this rewrite (Grammarly-style), or inject scoped guidance for the *model* to ask the right question — which converts the platform's improving prompt-handling from a threat into a tailwind.
- **Lead with reasons-to-install: secret-prevention + project-context — honestly.** These are the strong felt jobs, but they have real incumbents: gitleaks / trufflehog / git-secrets / GitHub push protection for secrets, and Claude Code's native `/init` for CLAUDE.md. cpl's wedge is **placement + convenience + local eval** at the prompt-submit checkpoint, not detection sophistication or novelty.
- **Target a painkiller SEGMENT, not the median subscriber.** For the median user cpl is a vitamin. For specific segments it's a painkiller: compliance-sensitive teams, API-metered heavy users, and prompt-discipline learners. Aim there.

**Why this position is strong:** the interception point is the asset — the last checkpoint before tokens are spent and before data leaves the machine, with full repo context, for free. Quality-scolding is a low-value use of that seat; safety + context injection is a high-value one.

## Open risks / things to validate

- **"Coach Claude" can backfire.** Per-prompt injected "ask about X" risks making Claude more interrogative and polluting context — the exact thing power users hate. Must fire only on anchor-free prompts via existing Tier-1 logic.
- **`init` needs auto-freshness to differentiate.** It collides head-on with native `/init` writing the same CLAUDE.md. The only real differentiator — owning AUTO-FRESHNESS / drift detection — is not yet built.
- **The secret surface is narrow at prompt-submit.** The UserPromptSubmit hook never sees the bigger agentic leak vector (an agent reading `.env` into context). Validate that the prompt-submit slice is a meaningful enough surface to be a primary install reason.

## Recommended first moves

1. Re-author the gate's response: ship the accept-this rewrite path and/or scoped "coach Claude" injection; demote warn-mode auto-gate to opt-in.
2. Reposition the README/marketing around safety + context as the day-one install reason, with honest incumbent framing (wedge = placement/convenience/local).
3. Pick and name the beachhead segment (compliance teams / API-metered / learners) and tailor the pitch to it.
4. Build `init` auto-freshness (drift detection) so project-context has a real differentiator vs native `/init`.
5. Create one shareable / try-before-install artifact (no-install rewriter playground or before/after gallery) to seed a value-first loop.
