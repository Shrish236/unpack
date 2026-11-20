# Unpack — Project Brief (final draft v1)

Date: 2026-11-20 · Event: Startup Buildathon India 2026 (Hack2skill, Google DeepMind + Google Cloud) · City buildathon 20–21 Nov, finale 2 Dec (Bengaluru)
Judging criteria published on the event page: founder profile, product potential, market viability, technical architecture, use of Google AI.

> **For Claude Code:** this file is the single source of truth for what to build. Sections 5–12 are the build spec. Sections 1–4 and 13–14 are context for the pitch. Follow the engineering rules in section 11. If something here conflicts with what the user says in chat, the user wins. Ask before changing scope.

---

## 1. One-liner and positioning

**Unpack checks what an AI agent says against what the developer asked and what actually happened, then turns those verified decisions — and the human overrides of the agent — into governed company knowledge that is fed back to every agent.**

Short pitch line: *Step 1 makes each PR trustworthy to read. Step 2 makes the whole agent programme trustworthy to run.*

Problem statement (use verbatim):

> Agents now make engineering decisions all day — which dependency to add, what schema to use, whether to skip a test. Nobody records, compares or governs those decisions. Companies cannot tell whether teams make the same decision the same way, which decisions turned out badly, or whether any policy was followed.

---

## 2. PARK (for the mentor)

### P — Problem
- Developer level: agents write PRs faster than people can understand them ("comprehension debt"). Reviewers read the agent's own narration, which is self-authored evidence.
- Company level: no evidence base for where agents can be trusted, no record of who understands which code, no way to see repeated or conflicting decisions across teams, no way to turn human corrections into policy.
- Why now (vendor/third-party reported, cite carefully): GitHub's 2026 Octoverse reports more than 40% of September PRs began with an agent's first draft. Qodo's own 2026 survey reports only 34.6% of developers say agents always follow their organisation's standards.
- Weak spot to admit: no customer interviews yet. Say "we will validate with reviewers", do not claim validation.

### A — AI and innovation
- Gemini reads the whole session and extracts: what the user asked, what the agent claimed, which function each edit touched, and where the human overrode the agent.
- **AI proposes, evidence decides.** Verification is deterministic (did tests run, did they pass, were there edits after the last run, does a covering test exist, is the claimed change in the diff). The LLM never grades its own claims.
- Anchor intent on the **user's turns** (human-authored ground truth), not the agent's narration. Show the agent's stated rationale only as "agent's stated rationale (unverified)".
- Innovation: verified, per-function decisions on a code graph, plus a company decision library with human approval and a feedback loop to agents.
- Google stack: Gemini (structured JSON output, long context so the whole session fits in one call where possible) via AI Studio or Vertex, Cloud Run for hosting. Optional: Gemma for local secret redaction (quality risk — treat as stretch).
- Be honest on novelty: the pieces exist separately (see section 4). The combination and the verification layer are the claim.

### R — Reality
- Real by the demo: one agent (Claude Code sessions), one language, tree-sitter graph, Gemini pipeline, deterministic checks, interactive graph page, override capture, one policy firing on the live demo PR.
- Mocked or seeded (must be labelled "simulated" in the UI): GitHub App comment, CLI hook, team-level history, outcome data.
- Skipped: Neo4j, commit picker, access checks, 24h caching, self-hosting, other agent adapters.
- Biggest risks: reason accuracy, false "untested" flags, sessions from cloud agents our local hook cannot see, competitors shipping the same loop (section 4).
- Path to market: free for individual developers running locally; paid team view (library, approval, monitoring); annual licence for self-hosted companies using their own model access. Consume existing session captures (Entire checkpoints, Git AI, Agent Trace) rather than competing on capture.

### K — unknown, confirm with mentor/organiser
We could not find a published definition of K. The event's five criteria map as: P = product potential + market viability, A = use of Google AI, R = technical architecture. The only criterion left is **founder profile**, so K may be about the team. Ready-made answers, pick one:

- **Team/founder reading:** "[your background]. I use agents daily and review their PRs, so I live this problem."
- **KPI/metrics reading:** headline metric = minutes to understand an agent PR with and without Unpack (target to be measured, e.g. 11 → 2). Product metrics = share of agent claims verified; share of changed functions with evidence; **repeat-override rate** (how often the same human correction recurs after its policy exists).
- **Knowledge-of-customer reading:** "Pain sits with reviewers on agent-heavy teams. Next: 5 reviewer interviews, 3 team pilots."

---

## 3. Product: two steps and one loop

**Step 1 — developer (per PR).** Per changed function show: origin label (requested / agent-initiated but related / unrequested), the user turn that asked for it, the agent's claims and their verdicts, struggle signals (repeated edits, reverts, failed runs), blast radius (callers), test coverage flag. Plus a PR summary and a link to the interactive graph.

**Step 2 — company (across PRs and time).** Every Step 1 verdict is stored permanently and aggregated:
1. **Decision ledger:** decisions by type (new dependency, data model, auth/security, error handling/retries, API contract, test strategy incl. skipping/deleting tests, config/infra, scope).
2. **Consistency:** same decision made differently across teams/agents.
3. **Outcomes:** link decisions to reverts, follow-up bug fixes, CI failures, review pushback, incidents. Report as *associated with*, never as causation. Humans decide good/bad.
4. **Earned autonomy (roadmap):** per agent/model/area verified-claim rate, unrequested-change rate. Autonomy must be reversible.
5. **Comprehension coverage (roadmap):** code no human has engaged with, weighted by caller count. Measure code and agents, never individual developers.
6. **Audit evidence (roadmap):** per-change pack — request, agent actions, verified claims, human review, tests.

**The learning loop (human overrides → policy).**
1. Capture moments where the human rejects, redirects, reverts or denies permission for what the agent proposed. Record: agent proposal, human choice, reason if given, area, quoted turn.
2. Aggregate. One developer = personal preference. Same override from several developers/teams = **policy candidate**.
3. A tech lead approves, edits or rejects; sets scope (repo/team/org), enforcement (advice | PR check | hard gate) and expiry.
4. Publish: generated AGENTS.md / skill snippet + PR check rule. Export so it works with any agent.
5. Measure adherence and repeat-override rate. If the override keeps happening, revise or retire. Every policy has an owner and an expiry so rules do not ossify.

### Why not just a prompt, skill file, memory or ADR
| Layer | Where it breaks |
|---|---|
| Prompt | One session only; negative constraints weaken as conversations grow. |
| Skill / AGENTS.md / CLAUDE.md | Stores rules but does not discover, approve, enforce or verify them; goes stale, bloats, conflicts, drifts across tools. |
| Agent auto-memory | Per developer / per tool / per repo; not visible company-wide. |
| ADR | Manual, so often abandoned; records decisions, enforces nothing. |
| Unpack | Discovery, aggregation, approval, scope, enforcement, adherence, expiry — and the files are an *output* of Unpack, not a competitor. |

Honest threshold: for one repo and a few developers a CLAUDE.md is enough. The pain starts with multiple teams, multiple agents and audit requirements.

---

## 4. Competitive landscape (public pages only, as of 2026-11-20 — verify before claiming absence)

**Session capture / attribution (our possible data source, not our fight):**
- Entire (ex-GitHub CEO Thomas Dohmke; $60M seed Feb 2026): captures sessions as checkpoints linked to commits via a commit trailer; `entire explain` AI summaries; Trails (launched 26 Oct 2026) puts session history into agent-run review with scored evals and merge gates; session-to-skill workflow. https://docs.entire.io
- Git AI: line-level AI attribution in git notes, survives rebases/squashes. https://usegitai.com
- Agent Trace: Cursor's open RFC spec for AI attribution, backed by several vendors. https://agent-trace.dev

**PR understanding / review:**
- CodeRabbit (Series C $143M at $1.5B; Change Stack layered walkthroughs and diagrams; Learnings from chat with optional approval). https://docs.coderabbit.ai/knowledge-base/learnings
- Devin Review (Cognition; free for PRs on regular GitHub repos; smart diff grouping, explanations). https://cognition.ai/blog/devin-review
- Greptile, Graphite, Cursor Bugbot, GitHub Copilot code review, Claude Code Review (bug-finding focus; benchmarks are vendor-run).

**Closest to our learning loop:**
- Blume: watches local agent sessions, turns repeated corrections into rules and skills (Claude Code, Codex, Cursor). https://www.producthunt.com/products/blume-codes
- Qodo Rule Miner: mines org PR review history into enforceable rules, links each to its source comment, suggested-mode human review, adoption/violation analytics. https://docs.qodo.ai/governance/rule-enforcement/rule-miner
- GitHub Copilot memory + "Dreaming" (Oct 2026): proposes memory and skill/instruction changes via PRs for team review; Copilot only. https://github.blog/changelog/2026-10-28-github-intelligence-puts-your-code-context-and-history-to-work
- Devin Knowledge: suggests knowledge from chat feedback, org-shared. https://docs.devin.ai/product-guides/knowledge
- Claude Code auto memory: writes notes from corrections, local to the machine.
- Unblocked: decision context from Slack/PRs/tickets via MCP for any agent. https://getunblocked.com
- Open-source/DIY: session-transcript miners (rule diffs for human review), SpecStory "lore" (multi-author candidate = team practice), agentreflect, lessonweaver, Pydantic's braindump (4,668 review comments → ~150 AGENTS.md rules).

**Verification / intent prior art:**
- Meta's ARCTIC paper (intent prediction from conversation logs, drift detection, code spotlight) — research, diff-level. https://arxiv.org/pdf/2607.29516
- groundtruth (open source): runs tests itself to check an agent's "all tests pass" on a working tree. https://github.com/msal2020/groundtruth

**Engineering-intelligence / AI-impact dashboards (aggregate layer):** Jellyfish, DX, LinearB, Span, Weave, Git AI enterprise. They measure adoption, AI share, speed, quality outcomes. We found no verified-claim or intent metrics there → Unpack could be a data source or partner.

**What we did NOT find:** a company-level, vendor-neutral decision library built from authoring-session human overrides, with per-function verified evidence on a code graph, decision type/consistency analytics, outcome linking and audit packs. "Learn rules from corrections" itself is **not** novel — do not headline it.

**Positioning rule:** "They learn rules. We govern decisions, with verified evidence, across every agent." Integrate (export to AGENTS.md, Copilot memory, Qodo rules; ingest from Entire/Agent Trace) rather than compete. Platform risk: GitHub, Entire or Qodo can copy this fast.

---

## 5. Hackathon scope (timeline is ~1.5 days)

**Must build**
1. Session adapter (Claude Code JSONL → Unpack Session Format).
2. Code graph (tree-sitter, one language, in-memory Graphology): nodes = file, function, class, test; edges = calls, imports, test_covers. Query: changed functions from a diff + one hop + their tests.
3. Reasoning + decision extraction pipeline (Gemini, JSON schema output).
4. Deterministic checks + flags + PR summary.
5. Override capture + policy candidate + approve → generated AGENTS.md snippet + one PR check.
6. Interactive page (React + Sigma.js + Graphology): changed region, highlighted nodes, side panel (callers, callees, tests, origin label, user-turn evidence, claims and verdicts, override).
7. Thin API + store (SQLite or JSON files) + Cloud Run deploy; base URL configurable.

**Mock / seed (label "simulated" in the UI)**
- Team screen: decision-type mix, one cross-team comparison, recurring override across ~10 seeded sessions, outcome flags.
- PR comment as markdown preview or screenshot (post with `gh` CLI only if time remains).

**Skip:** Neo4j, CLI git hook and commit trailer (run a script by hand; optional regex secret scrub), commit picker, access checks, 24h cache, self-hosting, static graph image, Mermaid fallback, other agent adapters, earned-autonomy and audit-pack screens (roadmap slides only).

---

## 6. Architecture

```
Claude Code session (.jsonl) ──► adapter ──► Unpack Session Format ─┐
git diff of the PR ─────────────────────────────────────────────────┤
repo checkout ──► tree-sitter ──► code graph ───────────────────────┤
                                                                    ▼
                                   pipeline: map edits→functions → Gemini extraction
                                   → deterministic checks → verdicts → store (permanent)
                                                                    ▼
                          API ──► interactive page (Sigma.js) · PR comment preview · team screen · policy flow
```

Keep each box replaceable. Keep all agent-specific logic inside the adapter.

### 6.1 Unpack Session Format (minimum)
```json
{
  "session_id": "string",
  "agent": "claude-code",
  "model": "string",
  "started_at": "iso8601",
  "turns": [
    {
      "id": "t12",
      "role": "user|assistant|tool",
      "ts": "iso8601",
      "text": "string",
      "tool_call": { "name": "string", "args": {}, "denied": false },
      "tool_result": { "exit_code": 0, "output_excerpt": "string" },
      "edits": [ { "file": "path", "start_line": 10, "end_line": 24, "op": "add|modify|delete" } ]
    }
  ]
}
```

### 6.2 DecisionRecord (one per changed function per PR; the unit of everything in Step 2)
```json
{
  "id": "string", "pr": "string", "repo": "string", "team": "string",
  "function": "path::name", "agent": "string", "model": "string",
  "decision_type": "dependency|data_model|auth_security|error_handling|api_contract|test_strategy|config_infra|scope|other",
  "origin": "requested|agent_initiated_related|unrequested",
  "user_evidence_turns": ["t3"],
  "agent_rationale": { "text": "string|null", "status": "unverified|no_reason_in_session", "turns": ["t12"] },
  "alternatives_considered": [ { "text": "string", "turns": ["t12"] } ],
  "claims": [ { "text": "string", "kind": "tests_pass|covered|no_breaking_change|file_changed|other",
                "verdict": "verified|contradicted|unsupported|unverifiable",
                "evidence": { "turns": ["t30"], "check": "tests_ran|stale_tests|covering_test|phantom_change" } } ],
  "struggle": { "edits": 0, "reverts": 0, "failed_runs": 0 },
  "blast_radius": { "callers": 0, "has_covering_test": false, "test_edge_basis": "static_estimate" },
  "human_engagement": [ { "user": "hashed-id", "ts": "iso8601", "action": "viewed_panel" } ],
  "outcomes": [ { "kind": "revert|bugfix|ci_fail|incident|review_pushback", "ref": "string", "ts": "iso8601" } ]
}
```

### 6.3 OverrideEvent, PolicyCandidate, Policy
```json
{ "override": { "id": "string", "session_id": "string", "turn": "t40", "kind": "redirect|reject|revert|permission_denied",
  "agent_proposal": "string", "human_choice": "string", "reason": "string|null",
  "area": "path or function", "decision_type": "string" } }
{ "policy": { "id": "string", "statement": "string", "status": "proposed|approved|rejected|active|expired",
  "scope": "repo|team|org", "enforcement": "advice|check|gate", "owner": "string", "expires": "date",
  "source_overrides": ["id"], "distinct_developers": 0, "evidence_turns": ["..."],
  "outputs": { "agents_md_snippet": "string", "pr_check_rule": "string" },
  "metrics": { "repeat_override_rate_before": 0.0, "repeat_override_rate_after": 0.0 } } }
```

---

## 7. Pipeline rules

**Edit → function mapping:** use edit line ranges from the session and the diff, resolved against tree-sitter function spans. If an edit cannot be mapped (moved/renamed code), mark `unmapped`, do not guess.

**Gemini extraction (structured JSON only):** per function, give the user turns and the assistant turns leading up to the edit. Ask for: decision_type, origin label with the supporting *user* turn id, agent rationale (or null), alternatives, claims. Reject any output field that lacks turn ids. If the model cannot support a field with a turn id, store `null` / `no_reason_in_session`.

**Deterministic checks (no LLM):**
- `tests_ran`: parse test-command tool results in the session (pytest/jest etc.): ran at all, passed/failed counts.
- `stale_tests`: any edit to the function's file after the last test run.
- `covering_test`: graph `test_covers` edge exists. Always label `static_estimate`; never present as measured coverage.
- `phantom_change`: claimed file/function not in the diff.
- `new_dependency`: diff touches a manifest (package.json, requirements.txt, pyproject.toml, go.mod…).
- `unrequested`: LLM label must be cross-checked: no user turn mentions the file/area/dependency.

**Override detection:** classify each user turn that follows an agent proposal as accept / redirect / reject. Heuristic hints (negations, "instead", "don't") only assist the LLM; deterministic signals (permission denied, user edit removing agent lines) are strong. Store the quoted turn.

**Policy candidate rule (seeded for demo):** same normalised override pattern from ≥3 sessions and ≥2 distinct developers (configurable).

**Flags for the PR comment:** untested changed functions, stale tests, contradicted/unsupported claims, unrequested changes, new dependencies, low-confidence reasons.

---

## 8. Demo storyline (rehearse; pre-record the session so it cannot fail live)

1. Demo repo (mid-sized open source, one language). Plant the case: the agent claims "full test coverage" but skips one error path, and quietly adds one change nobody asked for (e.g. a new dependency).
2. In the same session the developer redirects the agent once: *"don't add a new library, use the existing HTTP client"* → captured as an override.
3. Open the PR graph: changed functions highlighted; panel shows user-turn evidence, claim verdicts, `untested` flag, `unrequested` label.
4. Trace-a-bug finish: paste a stack trace → highlights the culprit function, the session turn that produced it and what the user asked at that moment (target: under one minute).
5. Team screen (seeded, labelled simulated): same override recurring across ~10 sessions and 3 teams → **policy candidate** → click Approve → generated AGENTS.md rule + PR check.
6. The check fires on the next PR where an agent adds a library. Close with the repeat-override metric.

---

## 9. Build order and cut line

M0 pick demo repo + record planted session → M1 graph + "changed functions + one hop" query → M2 session adapter → M3 Gemini extraction (check output by hand) → M4 deterministic checks + flags → M5 interactive page → M6 override capture + policy approve + generated rule/check → M7 seeded team screen → M8 deploy to Cloud Run + rehearse.

**Do not start M5 until M3 output looks right.** If behind, cut in this order: M7 (use a slide), then the approval UI (use CLI output), then the stack-trace finish.

---

## 10. Acceptance criteria

- Run extraction on ≥10 real sessions; reviewer checks by hand. Target ≈ 8/10 correct reasons/origin labels, else reduce claims and show more "no reason in session".
- Zero reasons displayed without turn evidence.
- No false "untested" flag on the demo repo's well-tested functions (check manually; label basis as static estimate).
- Demo path runs end to end three times in a row from a clean start.
- All seeded data visibly labelled "simulated".

---

## 11. Engineering rules for Claude Code

1. Never show a reason, label or verdict without turn-id evidence. Missing → "no reason given in session".
2. Verification is deterministic code, not an LLM judgement. The LLM extracts; code checks.
3. Treat agent narration as unverified. Anchor intent on user turns.
4. Store verdicts, labels and policies as structured records permanently; do not regenerate.
5. Keep agent-specific parsing only in the adapter. Core code sees only Unpack Session Format.
6. Scrub secrets (API keys, .env values, tokens) before sending anything to a model or storing it; transcript quotes only behind the authenticated view, never in the PR comment.
7. Keep the server base URL configurable.
8. Measure agents, areas and code — never rank or score individual developers. Hash user ids.
9. Seeded/simulated data must be flagged in data and UI.
10. Report outcomes as "associated with", never as causes.
11. Do not copy code from GitNexus (non-commercial licence); build the graph from scratch.
12. Prefer small, working vertical slices; commit often; no scope additions without asking.

---

## 12. Suggested stack (open decisions in section 14)

Backend Python + FastAPI (fast to integrate tree-sitter and Gemini) or Node/TypeScript; tree-sitter for one language; Graphology in memory; SQLite/JSON store; React + TypeScript + Sigma.js for the page; Gemini through Google AI Studio or Vertex with response-schema JSON; Cloud Run.

---

## 13. Likely mentor questions

- **"Isn't this a wrapper around an LLM?"** The checks are deterministic and the asset is the stored verdict history.
- **"Isn't this ADRs?"** ADRs are manual and often abandoned; ours are captured automatically, verified, compared across teams and tied to enforcement.
- **"Blume / Qodo / Copilot memory already learn rules."** Yes. They learn rules; we govern decisions with verified evidence, from authoring sessions, across every agent, and export to their formats.
- **"Who decides what is a bad decision?"** Humans. Unpack shows outcome evidence; the company sets policy.
- **"What if the agent's reason is wrong?"** We anchor on the user's words and on verifiable facts; agent rationale is labelled unverified.
- **"Why would a company pay?"** Governance, audit evidence and safer autonomy; free for individuals, paid team/self-hosted tiers.
- **"What stops Entire/GitHub copying it?"** Nothing permanent. Edge = verification accuracy, neutrality across agents, and the accumulated verdict/outcome dataset.

---

## 14. Open decisions (ask the user)

1. What does K stand for? (section 2)
2. Target language for the demo repo and the demo repo itself.
3. Backend language (Python recommended, Node acceptable).
4. Who presents and what is the founder/team story for K.
5. Whether to post a real PR comment via `gh` or keep it a preview.

---

## 15. Roadmap (slide only, do not build now)

Commit-by-commit graph history; pre-merge preview of how a change reshapes the codebase; MCP so agents can query reasons, decisions and "do not undo" notes; CI gate on unverified claims; real coverage data instead of static test edges; earned-autonomy policy; comprehension-coverage map; audit packs; adapters for Cursor, Gemini CLI, Codex, Copilot; ingest Entire/Git AI/Agent Trace; optional "explain-back" comprehension check (gimmick risk).

---

## 16. Reference links

- Event: https://startupbuildathon.com/
- Entire docs: https://docs.entire.io · Trails coverage: https://www.i-scoop.eu/entire-trails-agentic-code-review/
- Git AI: https://usegitai.com · Agent Trace: https://agent-trace.dev
- CodeRabbit Learnings: https://docs.coderabbit.ai/knowledge-base/learnings
- Devin Review: https://cognition.ai/blog/devin-review · Devin Knowledge: https://docs.devin.ai/product-guides/knowledge
- Qodo Rule Miner: https://docs.qodo.ai/governance/rule-enforcement/rule-miner
- GitHub Copilot memory / Dreaming: https://github.blog/changelog/2026-10-28-github-intelligence-puts-your-code-context-and-history-to-work
- Blume: https://www.producthunt.com/products/blume-codes · Unblocked: https://getunblocked.com
- Meta ARCTIC (intent/drift): https://arxiv.org/pdf/2607.29516 · groundtruth: https://github.com/msal2020/groundtruth
- Agent-count stat source: https://www.developer-tech.com/?p=110902
