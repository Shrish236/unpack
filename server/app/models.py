"""SQLAlchemy ORM models defining the database schema (server design §4)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

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
