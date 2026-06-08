# Phase B — Design Spec (working draft)

> Status: working draft. Sections marked **OPEN DECISION** need a ruling before implementation. Everything else reflects decisions already made.
>
> Framing: this is an **evolution of Phase A**, not a rewrite. Phase A (single-agent-with-tools, 7 nba_api/Tavily tools, ~13k-char prompt with hard constraints + self-audit, Telegram delivery) stays the foundation. Phase B adds a second model, an orchestration layer, possession-level computation, and a verification pipeline — reusing the existing tools, prompt craft, and delivery wherever possible.

---

## 1. Purpose & scope

**What Phase B is:** a conversational companion for a *single* team (Celtics), doing one bounded loop well — **brief + spar**:

- *Brief* — "how is my team doing?" → a structured, evidence-backed brief with the skeptic's stress-test attached.
- *Spar* — "I think their defense is the problem" → analyst + skeptic respond, backing or challenging the take with computed data and cited expert opinion.

**Value proposition (the bar every feature serves):** computes numbers that exist as text nowhere (garbage-time-filtered ratings, on/off splits from raw play-by-play), attributes every claim to a computation or a source, and runs a second model on a different base to stress-test the narrative before the user sees it. *A general LLM summarizes what's already written; this computes what isn't, and verifies it.*

**Out of scope (later phases, will be built later on, not now in this phase):**
- Matchup mode (two-team preview) — Phase C.
- References-finder + coach/teacher agent — Phase D.
- Multi-team, scheduled pushes, persistence beyond a session, web UI.

---

## 2. Reuse / refactor / add (the build-on map)

Mapped against the current files.

**Reuse as-is:**
- `config.py` — team resolution + `CURRENT_SEASON`. (Add config for the second model + qualitative provider.)
- The 7 existing tools in `tools.py` — `get_team_status`, `get_team_season_stats`, `get_team_advanced_stats`, `get_team_recent_games`, `get_team_players`, `get_team_injuries`, `get_analytical_articles`.
- `telegram_bot.py` delivery — whitelist, chunking, typing indicator. The transport layer doesn't change.

**Refactor:**
- Extract the big system prompt out of `agent.py` into a `prompts/` module so prompts are iterable artifacts, not buried in code.
- Split `tools.py` into a `tools/` package as it grows (basic nba_api / advanced pbpstats / qualitative).
- `run.py` — evolve from "one team query → one report" into driving the orchestrator and holding per-chat session state.

**Add:**
- `agents/` — `analyst.py` (evolved from the Phase A prompt) and `critic.py` (different model + verification protocol).
- `orchestrator.py` — the LangGraph flow wiring intent → analyst → critic → synthesis, with session state.
- `tools/nba_advanced.py` — the pbpstats-based computation tools (the non-published numbers).
- `tools/qualitative.py` — Perplexity-backed expert synthesis (alongside the existing Tavily search).
- `schemas.py` + `validators.py` — Pydantic claim schema and the deterministic provenance gate.
- `tests/` — unit tests for the computation tools and the validator (your CV says "modular, with tests"; Phase A has none).

---

## 3. Architecture — orchestrated two agents, presented as a chat

**Principle:** the user *sees* a group chat with distinct voices (Analyst, Skeptic); under the hood the flow is a **deterministic orchestration**, not free-form agent-to-agent chatter. Controlled, traceable, debuggable — and "controlled orchestration that reads like a conversation" is a stronger engineering story than "agents talk and we hope."

**Brief flow:**
1. **Intent router** (lightweight) — classify the message: brief / spar / question.
2. **Analyst gather** — calls data tools (existing nba_api + new pbpstats computations) + qualitative tool (Perplexity) + odds signal. Emits a *draft* as structured claims, each carrying provenance (see §5).
3. **Provenance gate** (deterministic) — reject/flag any claim missing a source or computation. No LLM judgment here; it's a schema check.
4. **Critic review** (different model) — statistical stress-test of the surviving claims: sample size, trend-vs-noise, confounders, overreach. Emits per-claim verdicts + a narrative-level check.
5. **Synthesis** — reconcile: revise or drop weak claims, *surface* the skeptic's flags rather than hide them, assemble the final brief.
6. **Delivery** — Telegram (reuse Phase A chunking).

**Spar flow** (shorter):
1. Intent = spar; extract the user's claim ("their defense is the problem").
2. Analyst pulls the *specific* computed data to evaluate that claim (e.g., DEF rating trend + on/off + sample window) — reusing session data where already fetched.
3. Critic stress-tests both the user's claim and the analyst's read.
4. Synthesis: a grounded response that backs or challenges the take, with the dissent attached and traceable.

**State:** Phase A was stateless. Phase B needs **session-scoped state** (in-memory per chat): the team in focus, the data already fetched this session (so the spar reuses the brief's pulls instead of re-querying), and conversation history. LangGraph (already a dependency) handles this via its state/checkpoint model — build on it. Persistence across sessions is later.

---

## 4. The two agents

**Analyst (Claude).** Evolves directly from the Phase A prompt and its discipline — hard constraints, no fabrication, evidence-only, the locked role vocabulary in §"Key Players". New responsibilities: emit claims as structured objects (not free prose) so they can be gated and reviewed; call the new computation tools; integrate the qualitative layer.

**Critic / Skeptic (different model).** Its job is adversarial reasoning over the analyst's output, *not* retrieval. It needs strong reasoning, so its brain should be a capable reasoning model from a **different provider** than the analyst — the decorrelated-errors rationale the whole pitch rests on.

> **OPEN DECISION 4.1 — critic's model provider.** Recommendation: a non-Claude reasoning model (e.g., GPT-5.x or Gemini) so errors genuinely decorrelate from the Claude analyst. Cost: one more API key + provider dependency. Fallback if you want to stay single-vendor for now: a different *Claude* model (e.g., Opus as critic vs Sonnet as analyst) — simpler, but weaker decorrelation and a softer interview claim. *Your call.* Note: Perplexity is **not** the critic's brain — its strength is retrieve-and-cite, not stress-testing.

---

## 5. Fact-checking pipeline (the differentiator)

Two layers — deterministic first, then statistical judgment.

**Layer 1 — provenance gate (deterministic, no LLM).** The analyst must emit each claim as a structured object, e.g.:

```python
class Claim(BaseModel):
    text: str                 # the assertion, in words
    value: float | str | None # the number, if any
    source: str               # tool name, computation id, or cited URL
    sample_size: int | None   # possessions or games behind the number
    window: str | None        # e.g. "season", "last 10 games"
    kind: Literal["computed", "retrieved", "cited_opinion"]
```

A validator rejects any `computed`/`retrieved` claim with no `source`, and routes claims to the right scrutiny. This is the Law-1 idea ("hypothesis ≠ answer; every claim carries its evidence") enforced in code, not left to the prompt.

**Layer 2 — critic's statistical checks (LLM, different model).** On the gated claims:
- **Grounding** — is the number actually in a tool result? (ungrounded → reject)
- **Sample size** — enough possessions/games to support the claim? (small-sample narrative → flag)
- **Trend vs noise** — is a "recent shift" outside normal variation, or a blip? (compare window to season; use a variation/CI sense-check)
- **Confounders** — is the apparent effect explained by schedule strength, injuries, or garbage time?
- **Overreach** — does the narrative claim more than the data supports?

Critic output per claim: `confirm | flag_small_sample | flag_confounder | dissent_with_alternative | reject_ungrounded`, plus one narrative-level stress-test.

> **OPEN DECISION 5.1 — the statistical thresholds.** This is squarely your wheelhouse, so you should set it: what minimum sample (possessions / games) counts as "enough" for a claim; how a "real trend" is defined (e.g., recent window outside ±1 SD of season, or a simple CI check); which confounders the critic must always consider. I can propose defaults, but the rigor here is your edge — define it and the whole differentiator gets sharper.

---

## 6. Data layer

**Reuse (nba_api, Phase A tools):** team status, traditional + advanced season stats with ranks, recent games, roster/minutes, injuries (Tavily), analytical articles (Tavily). No change to the working logic.

**Add (pbpstats — the non-published numbers).** pbpstats parses play-by-play into possessions (it pulls from the same stats.nba.com endpoints nba_api uses; all of pbpstats.com is derived from it), which lets us compute the CtG-style metrics *from raw data*:
- **Garbage-time-filtered ratings** — OFF/DEF/NET recomputed after removing low-leverage possessions.
- **On/off splits** — team net rating with a key player on vs off the floor (the "player impact" number).
- **Recent-form on a possession basis** — last N games, garbage time removed.

> **OPEN DECISION 6.1 — the v1 computed-stat set.** Computing each of these from possessions is real work; pick the 2–3 most worth it for a single-team companion. Recommendation: (a) garbage-time-filtered NET/OFF/DEF, (b) on/off splits for the top rotation, (c) possession-based recent form. Prioritize for analytical value + demo impact. *Your call.*

> **OPEN DECISION 6.2 — definition of "garbage time."** Methodological, and yours to own. Simple version: score-margin + time-remaining cutoff (CtG-style). Rigorous version: pbpstats can group possessions by win-probability impact, so "low-leverage" is defined by WP rather than a crude margin rule — a sharper flex than CtG's filter. Pick the definition; it propagates through every computed stat.

**Engineering caveats (for the spec → Code):**
- pbpstats hits undocumented stats.nba.com endpoints — rate-limited and occasionally breaks. **Cache raw possession pulls aggressively** (per game id) so we don't refetch.
- On/off from possessions requires careful lineup parsing — this is where the unit tests matter most.

**Qualitative layer (Perplexity).** Add a Perplexity-backed tool that returns *synthesized, cited* expert takes on a specific question ("what are analysts saying about the Celtics' defense this month"), distinct from Tavily's raw-result search. Honest framing: retrieval-and-cite is Perplexity's specialty and cheaper than bolting search onto a general model — we own the computation and the critic, not the qualitative citation.

> **OPEN DECISION 6.3 — stage Perplexity now or later in Phase B.** It's an enhancement; the two-agent + computed-stats core is the priority. Add Perplexity within Phase B, or keep Tavily-only for the first working version and layer Perplexity after. *Low-stakes; your preference.*

**Odds signal.** Pull market lines from an aggregator (free tier) as a *market-baseline signal* the critic can use ("the line disagrees with the emerging narrative"). Not a betting feature. Likely deferred to once the brief + spar core works — flag, don't build first.

---

## 7. Output structures

**Brief** (evolves the Phase A 6-section report; tighter, plus the skeptic's voice):
1. Header — team, date, status (reuse).
2. State read — record/trend, what's working, what's not — now driven by *computed* stats (garbage-time-filtered, on/off), not raw nba_api alone.
3. Key players — reuse the Phase A section 4 + locked role vocabulary as-is.
4. **Skeptic's flags** (new) — 1–3 stress-test notes: small-sample warnings, confounders, counter-reads.
5. Sources — traceability: computations + cited expert takes.

**Spar** (short): the user's take → analyst's grounded read → skeptic's check → reconciled bottom line, each line traceable.

> **OPEN DECISION 7.1 — brief length/shape.** The Phase A report is long and detailed. For a conversational companion, confirm whether the brief stays that comprehensive or trims to a scannable core with detail on request. *Your preference.*

---

## 8. Proposed module structure

```
config.py                 # reuse + second-model/provider config
schemas.py                # Pydantic Claim model (new)
validators.py             # deterministic provenance gate (new)
tools/
  nba_basic.py            # the existing 7 tools, moved here
  nba_advanced.py         # pbpstats computations (new)
  qualitative.py          # Perplexity + Tavily (new)
prompts/
  analyst_prompt.py       # extracted + evolved from agent.py (new home)
  critic_prompt.py        # the critic's protocol (new)
agents/
  analyst.py              # analyst wiring (Claude)
  critic.py               # critic wiring (different model)
orchestrator.py           # LangGraph flow + session state (new)
run.py                    # drives orchestrator, holds session state
telegram_bot.py           # reuse delivery
tests/                    # computation tools + validator (new)
```

---

## 9. Tech / dependencies

- Keep **LangChain / LangGraph** (already in `requirements.txt`) — LangGraph is the right fit for the stateful, orchestrated, two-agent flow. Evolve from `create_agent` (single agent) to an explicit `StateGraph`.
- **Pydantic** — claim schemas + structured outputs (the provenance gate).
- Add **pbpstats**.
- Add the **second provider's SDK** (decision 4.1) if non-Claude.
- Add **Perplexity (Sonar API)** (decision 6.3) when staged.

---

## 10. Open decisions to resolve before Code builds

1. **4.1** — Critic's model provider (different vendor vs different Claude).
2. **5.1** — Statistical thresholds the critic enforces (your wheelhouse).
3. **6.1** — The v1 computed-stat set (which 2–3).
4. **6.2** — Definition of "garbage time" (margin/time vs win-probability).
5. **6.3** — Stage Perplexity now or after the core (low-stakes).
6. **7.1** — Brief length/shape.

Lock these → finalize this spec → engineer the analyst + critic prompts (building on the Phase A prompt) → hand to Claude Code.
