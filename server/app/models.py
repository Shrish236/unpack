"""SQLAlchemy ORM models defining the database schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any
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
    default_branch = Column(Text, default="main")
    installation_id = Column(BigInteger, nullable=True)
    ingest_token_hash = Column(Text, nullable=True)
    graph_built_sha = Column(Text, nullable=True)
    status = Column(Text, default="active")  # active | app_missing | disabled
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("owner", "name", name="uq_repo_owner_name"),)


class Push(Base):
    __tablename__ = "pushes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    repo_id = Column(BigInteger, ForeignKey("repos.id"), nullable=False)
    branch = Column(Text, nullable=False)
    base_sha = Column(String(40), nullable=False)
    head_sha = Column(String(40), nullable=False)
    payload_path = Column(Text, nullable=True)
    has_session = Column(Boolean, default=False)
    redaction_counts = Column(JSONB, default=dict)
    cli_version = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("repo_id", "head_sha", name="uq_push_repo_head_sha"),)


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    push_id = Column(BigInteger, ForeignKey("pushes.id"), unique=True, nullable=False)
    public_id = Column(String(32), unique=True, nullable=False)
    status = Column(Text, default="queued")  # queued | running | done | failed
    error_code = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    stats = Column(JSONB, default=dict)
    facts = Column(JSONB, default=dict)
    graph_view = Column(JSONB, default=dict)
    llm_raw = Column(JSONB, nullable=True)
    llm_model = Column(Text, nullable=True)
    prompt_version = Column(Integer, default=1)
    rejected_count = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    push_id = Column(BigInteger, ForeignKey("pushes.id"), unique=True, nullable=False)
    agent = Column(Text, nullable=False)
    file_name = Column(Text, nullable=False)
    turns = Column(JSONB, default=list)


class FunctionReason(Base):
    __tablename__ = "function_reasons"

    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), primary_key=True)
    node_id = Column(Text, primary_key=True)
    reason = Column(Text, nullable=False)
    driver = Column(Text, nullable=False)  # user_asked | agent_decided | not_stated
    history = Column(Text, nullable=True)
    confidence = Column(Text, default="high")
    evidence = Column(JSONB, default=list)
    source = Column(Text, default="session")


class ReviewFinding(Base):
    __tablename__ = "review_findings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), nullable=False)
    kind = Column(Text, nullable=False)
    finding = Column(Text, nullable=False)
    functions = Column(JSONB, default=list)
    evidence = Column(JSONB, default=list)


class TrackedBranch(Base):
    __tablename__ = "tracked_branches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    repo_id = Column(BigInteger, ForeignKey("repos.id"), nullable=False)
    branch = Column(Text, nullable=False)
    latest_push_id = Column(BigInteger, ForeignKey("pushes.id"), nullable=True)
    latest_head_sha = Column(String(40), nullable=True)
    status = Column(Text, default="waiting_for_pr")  # waiting_for_pr | linked | closed_recently | abandoned
    needs_publish = Column(Boolean, default=True)
    next_check_at = Column(DateTime(timezone=True), server_default=func.now())
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    check_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("repo_id", "branch", name="uq_tracked_branch"),)


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
    state = Column(Text, default="open")  # open | closed | merged
    comment_id = Column(BigInteger, nullable=True)
    comment_url = Column(Text, nullable=True)
    last_published_analysis_id = Column(BigInteger, nullable=True)
    last_body_hash = Column(Text, nullable=True)
    last_published_at = Column(DateTime(timezone=True), nullable=True)
    etag = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (UniqueConstraint("repo_id", "number", name="uq_repo_pr_number"),)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(Text, nullable=False)  # analyze_push | render_image | publish_comment
    payload = Column(JSONB, default=dict)
    status = Column(Text, default="queued")  # queued | running | done | failed
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    run_after = Column(DateTime(timezone=True), server_default=func.now())
    locked_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    dedupe_key = Column(Text, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Render(Base):
    __tablename__ = "renders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), nullable=False)
    file_name = Column(String(64), unique=True, nullable=False)
    width = Column(Integer, default=1200)
    height = Column(Integer, default=700)
    bytes = Column(BigInteger, default=0)
    status = Column(Text, default="queued")  # queued | done | failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id = Column(BigInteger, ForeignKey("analyses.id"), nullable=False)
    purpose = Column(Text, nullable=False)  # reasons | reasons_part | json_repair
    model = Column(Text, nullable=False)
    attempt = Column(Integer, default=1)
    prompt_version = Column(Integer, default=1)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    thinking_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, default=0)
    status = Column(Text, default="ok")
    error = Column(Text, nullable=True)
    finish_reason = Column(Text, nullable=True)
    request_hash = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
