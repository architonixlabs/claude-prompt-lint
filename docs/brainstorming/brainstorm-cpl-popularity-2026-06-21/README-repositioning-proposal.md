# README Repositioning Proposal — claude-prompt-lint (`/cpl`)

> This is a **proposed repositioning of the README's *top*** — the title, tagline,
> and lead "Why" paragraph — not a code change. It encodes the session's
> **refined thesis**: keep the local prompt-eval engine as the IP, but change its
> response modality from *scold* to *offer/coach*, lead with the painkiller jobs
> (secret-prevention, project-context) at the privileged interception point, and
> name the segment honestly. Nothing below touches behavior; it changes what the
> README *promises first*.

---

## Before (current live lead — quoted verbatim)

> # claude-prompt-lint (`/cpl`)
>
> > **Lint your prompt before you spend the token.**
>
> A local-first prompt-quality toolkit for Claude Code.
> It intercepts your prompt the moment you hit enter, evaluates it **on your own
> machine**, and flags weak prompts with actionable feedback — *before* any API
> tokens are spent on a clarification round-trip.

> ## Why
>
> Vague, under-specified prompts cost you twice: the model asks a clarifying
> question, then you re-send. That round-trip is paid in tokens *after* you hit
> enter — too late. `cpl` moves the check **before** send, and runs it locally so
> the checker itself costs **zero API tokens**.

**What this lead does wrong (per session):** it leads with the *weakest, most
annoying* job (the quality gate), framed as a save-tokens vitamin that only bites
API-metered users, and sells the engine as a *scold* ("flags weak prompts"). The
strong, felt jobs — never leak a secret, keep your repo legible to Claude — are
buried far below the fold.

---

## After (proposed replacement copy for the top of the README)

> # claude-prompt-lint (`/cpl`)
>
> > **The last thing that runs on your machine before a prompt leaves it.**
> > *(alt tagline: "Catch the secret. Hand Claude the context. Then — if you want — tighten the ask.")*
>
> `cpl` sits at the one privileged spot in your workflow: the moment you hit
> enter, on your own machine, with full repo context, **before a single token is
> spent and before any data leaves your laptop** — and it does that for free. It
> uses that spot for the two things every Claude Code repo actually needs on day
> one, and offers a third only if you ask.
>
> **1. Never leak a secret.** Every prompt is scanned locally before it leaves
> your machine. An API key, token, private key, or DB string is caught *here* —
> the last checkpoint — and handed back to you **already masked**, ready to
> resend. No key reaches the API in the first place.
>
> **2. Keep your repo legible to Claude.** `/cpl init` writes a concise,
> cpl-managed project summary into your `CLAUDE.md` so Claude starts every
> session knowing your stack, commands, and layout — at zero per-turn token cost,
> and without re-deriving it each time.
>
> **3. Tighten the ask — as an offer, not a scold.** The same local engine that
> can grade a prompt no longer erases-and-lectures. On a vague, anchor-free
> prompt it does one of two helpful things: **proposes a tightened rewrite you
> can accept** (Grammarly-style), or **coaches Claude to ask the one question
> that's missing** — working *with* the model's planning, not against it. The
> auto-gate is opt-in; the default is a quiet, additive suggestion you can ignore.
>
> Built for people who feel these as real pain, not nice-to-haves:
> **compliance-sensitive teams** who can't have a key cross the wire,
> **API-metered heavy users** paying for every clarification round-trip, and
> **anyone deliberately leveling up their prompt discipline.**

---

## What changes and why

| Change in the new lead | Session rationale |
|---|---|
| New tagline ("last thing that runs before a prompt leaves your machine") | First Principles: **the asset is the privileged interception point** — last checkpoint before tokens spent and before data leaves the machine, with full repo context, free. Lead with the position, not the gate. |
| Lead job #1 = **mask / never leak a secret** | Secret-leak prevention is the **strongest felt, scary, near-universal pain** — a far stronger install reason than "your prompt is vague." JTBD reframe: the hero feature was the weakest job; this was a buried side feature. |
| Lead job #2 = **`/cpl init` keeps repo legible to Claude** | Project-context injection is felt by everyone running Claude Code on a real repo and gets *more* valuable as agents act autonomously. Reposition cpl from nanny → day-one setup tool. |
| Quality gate **demoted to #3 and reframed as an OFFER** (rewrite-to-accept / coach Claude), opt-in by default | Analogical: **winners auto-fix or add visible value (ESLint/Prettier/Grammarly); they don't scold.** Refined thesis: keep the engine as IP, change its **response modality** from scold → offer/coach. A hook can't silently rewrite, so make the *accept-a-rewrite* and *coach-Claude* paths the hero behavior. |
| "Coach Claude to ask" framing | Breakthrough wildcard: **coach Claude, not the human** — converts the platform trend (Claude gets better at handling vague prompts) from existential threat into a **tailwind**. |
| **Name the segment** (compliance teams / API-metered / discipline learners) | The **median user only has a vitamin**, not a painkiller. Popularity is reachable only by targeting a segment that feels a painkiller — say who that is, honestly, instead of pitching everyone. |
| Drop "save the clarification token" as the headline Why | That pain is **small and felt by a minority** (API-metered only; Max/Pro feel no per-token cost) and the round-trip is cheap — too weak to carry the lead. |

---

## Honest caveats to keep (so the new copy doesn't overclaim)

- **Secret-prevention has strong incumbents** — gitleaks, trufflehog, git-secrets,
  GitHub push protection. cpl's wedge is **placement + convenience + local eval at
  prompt-submit**, *not* superior detection. And it only sees the
  `UserPromptSubmit` surface: it does **not** catch the agentic leak vector where
  an agent reads `.env` into context. Say "caught at the prompt boundary," not
  "nothing leaks."
- **`/cpl init` collides with Claude Code's native `/init`**, which writes the same
  `CLAUDE.md`. Differentiation is thin today — real separation would come from
  **auto-freshness / drift detection**, which isn't built yet. Don't imply uniqueness
  the code doesn't have; pitch convenience and the cpl-managed section, not a moat.
- **"Coach Claude" must be scoped**, firing only on anchor-free prompts via the
  existing Tier-1 logic — per-prompt "ask about X" injection risks making Claude
  more interrogative and polluting context, the exact thing power users hate.
