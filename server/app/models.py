"""SQLAlchemy ORM models defining the database schema (server design §4)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from .db import Base


class Repo(Base):
    __tablename__ = "repos"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    remote_url = Column(Text, nullable=True)
    default_branch = Column(Text, nullable=False, default="main")
    installation_id = Column(BigInteger, nullable=True)
    pulls_etag = Column(Text, nullable=True)  # ETag of the open-pull-request list (conditional polling)
    ingest_token_hash = Column(String(64), nullable=True, unique=True)
    graph_built_sha = Column(String(40), nullable=True)
    status = Column(Text, nullable=False, default="active")  # active | app_missing | disabled
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("owner", "name", name="uq_repo_owner_name"),)


class Push(Base):
    __tablename__ = "pushes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    repo_id = Column(BigInteger, ForeignKey("repos.id"), nullable=False)
    branch = Column(Text, nullable=False)
    base_sha = Column(String(40), nullable=False)
    head_sha = Column(String(40), nullable=False)
    commits = Column(JSONB, nullable=False, default=list)  # [{sha, message, author_time}]
    payload_path = Column(Text, nullable=True)
    has_session = Column(Boolean, nullable=False, default=False)
    session_agent = Column(Text, nullable=True)
    redaction_counts = Column(JSONB, nullable=False, default=dict)
    cli_version = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("repo_id", "head_sha", name="uq_push_repo_head_sha"),
        Index("ix_pushes_repo_received", "repo_id", "received_at"),  # push rate limit
        Index("ix_pushes_repo_branch", "repo_id", "branch"),
    )


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    push_id = Column(BigInteger, ForeignKey("pushes.id"), unique=True, nullable=False)
    public_id = Column(String(32), unique=True, nullable=False)
    status = Column(Text, nullable=False, default="queued")  # queued | running | done | failed
    error_code = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    banner = Column(JSONB, nullable=True)
    stats = Column(JSONB, nullable=False, default=dict)
    facts = Column(JSONB, nullable=False, default=dict)
    graph_view = Column(JSONB, nullable=False, default=dict)  # {nodes, edges, collapsed, truncated}
    reading_order = Column(JSONB, nullable=False, default=list)
    impact = Column(JSONB, nullable=False, default=dict)
    diff_hunks = Column(JSONB, nullable=False, default=dict)
    timeline = Column(JSONB, nullable=False, default=list)
    llm_model = Column(Text, nullable=True)
    prompt_version = Column(Integer, nullable=False, default=1)
    rejected_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class Session(Base):
    """Parsed agent session turns for a push."""

    __tablename__ = "sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    push_id = Column(BigInteger, ForeignKey("pushes.id"), unique=True, nullable=False)
    agent = Column(Text, nullable=False)
    file_name = Column(Text, nullable=False)
    turns = Column(JSONB, nullable=False, default=list)


class FunctionReason(Base):
    __tablename__ = "function_reasons"

    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), primary_key=True)
    node_id = Column(Text, primary_key=True)
    reason = Column(Text, nullable=False)
    driver = Column(Text, nullable=False)  # user_asked | agent_decided | not_stated
    history = Column(JSONB, nullable=False, default=list)  # [{turn, text}]
    confidence = Column(Text, nullable=False, default="high")
    evidence = Column(JSONB, nullable=False, default=list)
    source = Column(Text, nullable=False, default="session")
    rejected = Column(JSONB, nullable=True)  # hidden original LLM output when quotes fail verification


class ReviewFinding(Base):
    __tablename__ = "review_findings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), nullable=False)
    kind = Column(Text, nullable=False)
    finding = Column(Text, nullable=False)
    functions = Column(JSONB, nullable=False, default=list)
    evidence = Column(JSONB, nullable=False, default=list)


class TrackedBranch(Base):
    __tablename__ = "tracked_branches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    repo_id = Column(BigInteger, ForeignKey("repos.id"), nullable=False)
    branch = Column(Text, nullable=False)
    latest_push_id = Column(BigInteger, ForeignKey("pushes.id"), nullable=True)
    latest_head_sha = Column(String(40), nullable=True)
    status = Column(Text, nullable=False, default="waiting_for_pr")
    needs_publish = Column(Boolean, nullable=False, default=True)  # true while a post is pending
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    check_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("repo_id", "branch", name="uq_tracked_branch"),
        Index("ix_tracked_sweep", "status", "needs_publish"),  # the poller's pending-work scan
    )


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    repo_id = Column(BigInteger, ForeignKey("repos.id"), nullable=False)
    number = Column(Integer, nullable=False)
    tracked_branch_id = Column(BigInteger, ForeignKey("tracked_branches.id"), nullable=True)
    head_ref = Column(Text, nullable=False)
    head_sha = Column(String(40), nullable=False)
    base_ref = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    html_url = Column(Text, nullable=True)
    state = Column(Text, nullable=False, default="open")  # open | closed | merged
    comment_id = Column(BigInteger, nullable=True)
    comment_url = Column(Text, nullable=True)
    last_published_analysis_id = Column(BigInteger, nullable=True)
    last_body_hash = Column(Text, nullable=True)
    last_published_at = Column(DateTime(timezone=True), nullable=True)
    description_hash = Column(Text, nullable=True)  # hash of the Unpack section last written to the description
    compare_cache = Column(JSONB, nullable=True)  # {"key": "...", "result": {...}}: last compare decision
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_repo_pr_number"),
        Index("ix_pr_tracked_branch", "tracked_branch_id"),
    )


class PRAnalysis(Base):
    """Commit picker history: which analyses a pull request has been linked to."""

    __tablename__ = "pr_analyses"

    pr_id = Column(BigInteger, ForeignKey("pull_requests.id"), primary_key=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), primary_key=True)
    linked_at = Column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(Text, nullable=False)  # analyze_push | render_image | publish_comment | build_graph
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(Text, nullable=False, default="queued")  # queued | running | done | failed
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=4)
    run_after = Column(DateTime(timezone=True), server_default=func.now())
    locked_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    dedupe_key = Column(Text, unique=True, nullable=True)  # cleared when the job finishes
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_jobs_claim", "status", "run_after"),)  # queue claim


class Render(Base):
    __tablename__ = "renders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), nullable=False)
    file_name = Column(String(64), unique=True, nullable=False)
    width = Column(Integer, nullable=False, default=1200)
    height = Column(Integer, nullable=False, default=700)
    bytes = Column(BigInteger, nullable=False, default=0)
    status = Column(Text, nullable=False, default="queued")  # queued | done | failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LLMCall(Base):
    """Reserved for the reasoning step. Not written in this build."""

    __tablename__ = "llm_calls"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), nullable=False)
    purpose = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    prompt_version = Column(Integer, nullable=False, default=1)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    thinking_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=False, default=0)
    status = Column(Text, nullable=False, default="ok")
    error = Column(Text, nullable=True)
    finish_reason = Column(Text, nullable=True)
    request_hash = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OAuthState(Base):
    """Login states issued by /auth/login. Each state is accepted once (design §11)."""

    __tablename__ = "oauth_states"

    nonce = Column(String(64), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    github_id = Column(BigInteger, unique=True, nullable=False)
    login = Column(Text, nullable=False)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WebSession(Base):
    __tablename__ = "web_sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    oauth_token_encrypted = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class AccessCache(Base):
    __tablename__ = "access_cache"

    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    repo_id = Column(BigInteger, ForeignKey("repos.id"), primary_key=True)
    allowed = Column(Boolean, nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"

    worker_id = Column(String(64), primary_key=True)
    beat_at = Column(DateTime(timezone=True), server_default=func.now())


class Decision(Base):
    """One decision in a session: who made it, what it was about, and the verbatim quote that proves it."""
    __tablename__ = "decisions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    turn = Column(Integer, nullable=False)
    actor = Column(Text, nullable=False)  # agent | human
    kind = Column(Text, nullable=False)  # choice | redirect | reject | requirement | discussion | permission_denied
    type = Column(Text, nullable=False)  # architecture | design | dependency | retries | test | scope | other
    proposal = Column(Text, nullable=False, default="")
    choice = Column(Text, nullable=False, default="")
    statement = Column(Text, nullable=False, default="")  # the correction as a reusable rule, for clustering
    quote = Column(Text, nullable=False, default="")
    rule_id = Column(Text, nullable=True)  # steering rule id within this analysis's snapshot (S1, S2 ...)
    rule_followed = Column(Boolean, nullable=True)
    source = Column(Text, nullable=False, default="llm")  # parsed | llm
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_decisions_analysis", "analysis_id"),)


class SessionSignals(Base):
    """Deterministic signals, highlights and the steering snapshot for one analysis."""
    __tablename__ = "session_signals"

    analysis_id = Column(BigInteger, ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True)
    signals = Column(JSONB, nullable=False, default=dict)  # tool_stats, denied, attempts, flags ...
    highlights = Column(JSONB, nullable=False, default=list)  # [{kind: went_right|went_wrong, text, turn, quote}]
    steering = Column(JSONB, nullable=False, default=dict)  # {files, rules}


# ---------------------------------------------------------------------------------------------
# Dashboard tables. Aggregates for the executive, manager and governance pages. They are loaded
# with dummy data by server/app/dashboard_seed.py, and the governance actions write to them.
# Nothing here is measured yet; the seed says so.
# ---------------------------------------------------------------------------------------------


class ExecWeek(Base):
    """One week of the company-wide agent programme (executive page)."""
    __tablename__ = "exec_weeks"

    week_start = Column(Date, primary_key=True)
    adherence = Column(Integer, nullable=False)  # % of agent decisions that followed a skill rule
    repeat_overrides = Column(Float, nullable=False)  # the same human correction, per 100 sessions
    human_decisions = Column(Integer, nullable=False)
    mix = Column(JSONB, nullable=False)  # decisions by type, e.g. {"architecture": 18, ...}


class ExecPeriod(Base):
    """KPIs and criteria outcomes for one reporting window (30d or 90d)."""
    __tablename__ = "exec_periods"

    period = Column(Text, primary_key=True)
    adherence = Column(Integer, nullable=False)
    adherence_delta = Column(Integer, nullable=False)
    override = Column(Float, nullable=False)
    override_before = Column(Float, nullable=False)
    verified = Column(Integer, nullable=False)
    verified_delta = Column(Integer, nullable=False)
    unrequested = Column(Integer, nullable=False)
    unrequested_delta = Column(Integer, nullable=False)
    pending = Column(Integer, nullable=False)
    pending_oldest_days = Column(Integer, nullable=False)
    sessions = Column(Integer, nullable=False)
    rework_first = Column(Integer, nullable=False)
    rework_missed = Column(Integer, nullable=False)
    rework_thin = Column(Integer, nullable=False)


class ExecHumanKind(Base):
    """How human decisions entered the record, as a share of all human decisions."""
    __tablename__ = "exec_human_kinds"

    kind = Column(Text, primary_key=True)
    label = Column(Text, nullable=False)
    pct = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)


class ExecPolicyEvent(Base):
    """A policy publication, drawn as a marker on the adherence chart."""
    __tablename__ = "exec_policy_events"

    id = Column(Text, primary_key=True)  # policy id, e.g. P-12
    week_start = Column(Date, nullable=False)
    text = Column(Text, nullable=False)
    headline = Column(Boolean, nullable=False, default=False)  # the policy the page reports on


class ExecAgent(Base):
    """An agent tool or model, and how far its claims verify."""
    __tablename__ = "exec_agents"

    name = Column(Text, primary_key=True)
    tool = Column(Text, nullable=False)
    decisions = Column(Integer, nullable=True)
    verified = Column(Integer, nullable=True)  # %
    unrequested = Column(Integer, nullable=True)  # %
    attempts = Column(Float, nullable=True)
    autonomy = Column(Text, nullable=True)  # advice | check | gate
    position = Column(Integer, nullable=False)


class Team(Base):
    """A team, with its headline KPIs and criteria funnel for the last eight weeks."""
    __tablename__ = "teams"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    position = Column(Integer, nullable=False)
    prs = Column(Integer, nullable=False)
    prs_delta = Column(Text, nullable=False)
    attempts = Column(Float, nullable=False)
    attempts_delta = Column(Text, nullable=False)
    overrules = Column(Float, nullable=False)
    thin = Column(Integer, nullable=False)  # % of criteria that were thin
    unsupported = Column(Integer, nullable=False)  # % of PRs with an unsupported claim
    funnel_total = Column(Integer, nullable=False)
    funnel_first = Column(Integer, nullable=False)
    funnel_second_agent = Column(Integer, nullable=False)
    funnel_second_thin = Column(Integer, nullable=False)
    funnel_third_agent = Column(Integer, nullable=False)
    funnel_third_thin = Column(Integer, nullable=False)


class TeamArea(Base):
    """A code area a team works in (a path prefix)."""
    __tablename__ = "team_areas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Text, ForeignKey("teams.id"), nullable=False)
    path = Column(Text, nullable=False)
    position = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("team_id", "path", name="uq_team_area_path"),)


class TeamAreaWeek(Base):
    """Rework in one area in one week. attempts = 0 means no criteria that week."""
    __tablename__ = "team_area_weeks"

    area_id = Column(Integer, ForeignKey("team_areas.id", ondelete="CASCADE"), primary_key=True)
    week_start = Column(Date, primary_key=True)
    attempts = Column(Float, nullable=False)
    overrules = Column(Integer, nullable=False)


class TeamSuggestion(Base):
    """A proposed fix, from the brief or from the agent, with the PRs it came from."""
    __tablename__ = "team_suggestions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Text, ForeignKey("teams.id"), nullable=False)
    position = Column(Integer, nullable=False)
    cause = Column(Text, nullable=False)  # requirement-thin | agent-missed
    text = Column(Text, nullable=False)
    prs = Column(ARRAY(Integer), nullable=False)


class TeamMix(Base):
    """Decisions by type for one team, split between the agent and humans."""
    __tablename__ = "team_mix"

    team_id = Column(Text, ForeignKey("teams.id"), primary_key=True)
    type = Column(Text, primary_key=True)
    agent = Column(Integer, nullable=False)
    human = Column(Integer, nullable=False)


class TeamTool(Base):
    """Tool use across one team's agents."""
    __tablename__ = "team_tools"

    team_id = Column(Text, ForeignKey("teams.id"), primary_key=True)
    name = Column(Text, primary_key=True)
    calls = Column(Integer, nullable=False)
    tokens = Column(Integer, nullable=False)


class TeamPR(Base):
    """A recent PR with an agent session, for a team's PR list."""
    __tablename__ = "team_prs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    number = Column(Integer, nullable=False, unique=True)
    team_id = Column(Text, ForeignKey("teams.id"), nullable=False)
    title = Column(Text, nullable=False)
    area = Column(Text, nullable=False)
    week_start = Column(Date, nullable=False)
    agent = Column(Text, nullable=False)
    agent_decisions = Column(Integer, nullable=False)
    human_decisions = Column(Integer, nullable=False)
    overrules = Column(Integer, nullable=False)
    attempts = Column(Float, nullable=False)
    flags = Column(ARRAY(Text), nullable=False)  # unsupported | new-dependency | skipped-test | async-gap
    source = Column(Text, nullable=False, server_default="sample")  # sample | measured


class ConsistencyItem(Base):
    """A decision type that teams may decide differently."""
    __tablename__ = "consistency_items"

    id = Column(Text, primary_key=True)
    type = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    position = Column(Integer, nullable=False)


class ConsistencyRow(Base):
    """How one team decided a consistency question."""
    __tablename__ = "consistency_rows"

    item_id = Column(Text, ForeignKey("consistency_items.id", ondelete="CASCADE"), primary_key=True)
    team_id = Column(Text, ForeignKey("teams.id"), primary_key=True)
    approach = Column(Text, nullable=False)
    prs = Column(Integer, nullable=False)


class GovCandidate(Base):
    """An override that repeats across sessions, waiting for a decision. Status: open | approved | rejected."""
    __tablename__ = "gov_candidates"

    id = Column(Text, primary_key=True)
    pid = Column(Text, nullable=False, unique=True)  # the policy id it gets if approved
    statement = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    sessions = Column(Integer, nullable=False)
    teams = Column(Integer, nullable=False)
    developers = Column(Integer, nullable=False)
    trend = Column(ARRAY(Integer), nullable=False)  # overrides per week, oldest first
    per_hundred = Column(Integer, nullable=False)
    match = Column(Text, nullable=False)
    scope = Column(Text, nullable=False)  # repo | team | org
    enforcement = Column(Text, nullable=False)  # advice | check | gate
    owner = Column(Text, nullable=False)
    expires = Column(Date, nullable=False)
    first_seen = Column(Date, nullable=False)
    status = Column(Text, nullable=False, default="open")
    decided_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(Text, nullable=False, server_default="sample")  # sample | measured
    brief = Column(JSONB, nullable=True)  # what a reviewer needs to decide: split by team, rework, reach, fit, recommendation


class GovPolicy(Base):
    """A published policy. Status: active | retired | revised."""
    __tablename__ = "gov_policies"

    id = Column(Text, primary_key=True)
    statement = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    scope = Column(Text, nullable=False)
    scope_name = Column(Text, nullable=False)
    enforcement = Column(Text, nullable=False)
    owner = Column(Text, nullable=False)
    expires = Column(Date, nullable=False)
    adherence = Column(Integer, nullable=True)  # null while it is still being measured
    before = Column(Integer, nullable=False)  # overrides per 100 sessions before the policy
    after = Column(Integer, nullable=True)
    match = Column(Text, nullable=False)
    recurrence_sessions = Column(Integer, nullable=True)  # set when the same override still recurs
    recurrence_teams = Column(Integer, nullable=True)
    recurrence_developers = Column(Integer, nullable=True)
    status = Column(Text, nullable=False, default="active")
    published_on = Column(Date, nullable=True)
    target = Column(Integer, nullable=True)  # overrides per 100 sessions the policy is meant to reach
    review_on = Column(Date, nullable=True)  # when the owner checks whether it worked
    weekly = Column(ARRAY(Integer), nullable=True)  # overrides per 100 sessions per week since approval
    checks_flagged = Column(Integer, nullable=True)  # PRs the check flagged (null for advice)
    checks_wrong = Column(Integer, nullable=True)  # of those, how many a reviewer overrode as wrong


class GovEvidence(Base):
    """A human override, quoted from a session. Belongs to a candidate or to a policy's recurrence."""
    __tablename__ = "gov_evidence"

    id = Column(Text, primary_key=True)
    candidate_id = Column(Text, ForeignKey("gov_candidates.id", ondelete="CASCADE"), nullable=True)
    policy_id = Column(Text, ForeignKey("gov_policies.id", ondelete="CASCADE"), nullable=True)
    position = Column(Integer, nullable=False)
    session = Column(Text, nullable=False)
    pr = Column(Text, nullable=False)
    team = Column(Text, nullable=False)
    dev = Column(Text, nullable=False)  # hashed id, never a name
    turn = Column(Integer, nullable=False)
    kind = Column(Text, nullable=False)  # redirect | reject | permission_denied | revert | requirement | discussion
    occurred_on = Column(Date, nullable=False)
    proposal = Column(Text, nullable=False)
    choice = Column(Text, nullable=False)
    quote = Column(Text, nullable=False)
    source = Column(Text, nullable=False, server_default="sample")  # sample | measured


class GovSkillRule(Base):
    """A skill rule and how often agent decisions followed it."""
    __tablename__ = "gov_skill_rules"

    id = Column(Text, primary_key=True)
    position = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    skill = Column(Text, nullable=False)
    followed = Column(Integer, nullable=False)
    violated = Column(Integer, nullable=False)
    trend = Column(ARRAY(Integer), nullable=False)  # violations per week
    latest_pr = Column(Text, nullable=False)
    latest_turn = Column(Integer, nullable=False)
    source = Column(Text, nullable=False, server_default="sample")  # sample | measured


class GovHistory(Base):
    """A decision taken on a candidate or policy. seq orders the list, newest first."""
    __tablename__ = "gov_history"

    seq = Column(BigInteger, primary_key=True, autoincrement=True)
    id = Column(Text, nullable=False, unique=True)
    statement = Column(Text, nullable=False)
    outcome = Column(Text, nullable=False)  # approved | rejected | expired
    role = Column(Text, nullable=False)
    occurred_on = Column(Date, nullable=False)
    why = Column(Text, nullable=False)


DASHBOARD_TABLES = (
    "exec_weeks", "exec_periods", "exec_human_kinds", "exec_policy_events", "exec_agents",
    "teams", "team_areas", "team_area_weeks", "team_suggestions", "team_mix", "team_tools", "team_prs",
    "consistency_items", "consistency_rows",
    "gov_evidence", "gov_candidates", "gov_policies", "gov_skill_rules", "gov_history",
)
