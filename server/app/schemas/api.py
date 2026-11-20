"""Pydantic schemas: single source of truth for the API and frontend contract."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


# -------------------------------------------------------------
# Base Common Models
# -------------------------------------------------------------

class RepoRef(BaseModel):
    owner: str
    name: str
    remote_url: str | None = None
    default_branch: str = "main"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# -------------------------------------------------------------
# Ingest Contract
# -------------------------------------------------------------

class ChangedFilePayload(BaseModel):
    path: str
    old_path: str | None = None
    status: Literal["A", "M", "D", "R"]
    is_binary: bool = False
    base_content: str | None = None
    head_content: str | None = None
    truncated: bool = False


class CommitPayload(BaseModel):
    sha: str
    message: str
    author_time: str


class SessionPayload(BaseModel):
    agent: str
    agent_version: str | None = None
    file_name: str
    lines: list[dict[str, Any]] = Field(default_factory=list)


class ClientMetadata(BaseModel):
    cli_version: str = "0.1.0"
    os: str = "unknown"
    hook: str = "pre-push"


class IngestPayload(BaseModel):
    schema_version: int = 1
    repo: RepoRef
    branch: str
    base_sha: str
    head_sha: str
    commits: list[CommitPayload] = Field(default_factory=list)
    diff: str = ""
    changed_files: list[ChangedFilePayload] = Field(default_factory=list)
    session: SessionPayload | None = None
    redactions: dict[str, int] = Field(default_factory=dict)
    client: ClientMetadata = Field(default_factory=ClientMetadata)


class AnalysisRef(BaseModel):
    public_id: str
    status: Literal["queued", "running", "done", "failed"]
    url: str


class TrackingStatus(BaseModel):
    branch: str
    status: Literal["waiting_for_pr", "linked", "closed_recently", "abandoned", "untracked"]


class IngestResponse(BaseModel):
    push_id: int
    analysis: AnalysisRef
    tracking: TrackingStatus
    deduplicated: bool = False


# -------------------------------------------------------------
# Live Analysis Contract (UI & Renderer)
# -------------------------------------------------------------

class PullRequestInfo(BaseModel):
    number: int
    title: str
    url: str
    state: Literal["open", "closed", "merged"] = "open"


class Banner(BaseModel):
    kind: Literal["partial_coverage", "out_of_date", "reasons_unavailable", "no_session"]
    message: str


class AnalysisStats(BaseModel):
    functions_changed: int
    by_source: dict[str, int] = Field(default_factory=dict)
    by_change: dict[str, int] = Field(default_factory=dict)
    not_reached_by_tests: int = 0


class LastTestRun(BaseModel):
    turn: str
    command: str
    exit_code: int
    summary: str


class AnalysisFacts(BaseModel):
    last_test_run: LastTestRun | None = None
    tested_after_final_edit: bool = False


class NodeChange(BaseModel):
    kind: Literal["added", "functional", "signature", "text_only", "deleted"]
    source: Literal["session", "session_then_formatted", "session_partial", "outside_session"] = "session"


class NodeTest(BaseModel):
    label: Literal["direct", "reached", "reached_uncertain", "none"]
    count: int = 0
    shortest_path: list[str] = Field(default_factory=list)
    nearest_tested: str | None = None


class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["file", "class", "function", "method", "test"]
    parent: str | None = None
    path: str
    layer: Literal["container", "changed", "neighbor", "impact", "test", "ghost"] = "changed"
    start_line: int | None = None
    end_line: int | None = None
    signature: str | None = None
    is_async: bool = False
    is_public: bool = True
    bases: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    imports_total: int | None = None
    change: NodeChange | None = None
    test: NodeTest | None = None
    callers_count: int = 0
    callees_count: int = 0
    is_test: bool = False
    has_reason: bool = False
    finding_ids: list[int] = Field(default_factory=list)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: Literal["CALLS", "INHERITS", "OVERRIDES", "REACHES", "IMPORTS"]
    tier: Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"] | None = None
    via: str | None = None


class CollapsedGroup(BaseModel):
    id: str
    anchor: str
    direction: Literal["callers", "callees", "tests"]
    file: str
    count: int
    node_ids: list[str] = Field(default_factory=list)


class TruncatedInfo(BaseModel):
    nodes_omitted: int = 0
    edges_omitted: int = 0


class GraphPayload(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    collapsed: list[CollapsedGroup] = Field(default_factory=list)
    truncated: TruncatedInfo = Field(default_factory=TruncatedInfo)


class ImpactSummary(BaseModel):
    functions: int = 0
    files: int = 0
    public_api: int = 0
    uncertain_paths: int = 0


class ImpactHop(BaseModel):
    id: str
    depth: int
    tier: Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]
    uncertain: bool = False


class ImpactData(BaseModel):
    summary: ImpactSummary = Field(default_factory=ImpactSummary)
    by_node: dict[str, list[ImpactHop]] = Field(default_factory=dict)


class TimelineTurn(BaseModel):
    turn: str
    kind: Literal["user_request", "edit", "test_run", "claim", "out_of_band"]
    ts: str
    label: str
    nodes: list[str] = Field(default_factory=list)
    reverted: bool = False
    exit_code: int | None = None
    finding_id: int | None = None


class EvidenceQuote(BaseModel):
    turn: str
    quote: str


class HistoryStep(BaseModel):
    turn: str
    text: str


class FunctionReason(BaseModel):
    reason: str
    driver: Literal["user_asked", "agent_decided", "not_stated"]
    history: list[HistoryStep] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "high"
    source: str = "session"
    evidence: list[EvidenceQuote] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    id: int
    kind: Literal[
        "claim_not_backed",
        "test_failed_ignored",
        "not_tested_after_change",
        "request_not_done",
        "check_weakened",
        "dead_end"
    ]
    finding: str
    functions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceQuote] = Field(default_factory=list)


class DiffHunk(BaseModel):
    start_line: int
    end_line: int
    patch: str


class AnalysisMetadata(BaseModel):
    public_id: str
    status: Literal["queued", "running", "done", "failed"]
    repo: RepoRef
    branch: str
    base_sha: str
    head_sha: str
    short_sha: str
    created_at: str
    finished_at: str | None = None
    agent: str | None = None
    llm_model: str | None = None
    prompt_version: int = 1
    has_session: bool = True
    error_code: str | None = None
    error_message: str | None = None


class AnalysisResponse(BaseModel):
    """The master JSON contract served at GET /api/analyses/{public_id}."""
    analysis: AnalysisMetadata
    pull_request: PullRequestInfo | None = None
    banner: Banner | None = None
    summary: str = ""
    stats: AnalysisStats = Field(default_factory=lambda: AnalysisStats(functions_changed=0))
    facts: AnalysisFacts = Field(default_factory=AnalysisFacts)
    graph: GraphPayload = Field(default_factory=GraphPayload)
    reading_order: list[str] = Field(default_factory=list)
    impact: ImpactData = Field(default_factory=ImpactData)
    timeline: list[TimelineTurn] = Field(default_factory=list)
    reasons: dict[str, FunctionReason] = Field(default_factory=dict)
    findings: list[ReviewFinding] = Field(default_factory=list)
    diff_hunks: dict[str, list[DiffHunk]] = Field(default_factory=dict)


# -------------------------------------------------------------
# Secondary Live Endpoints
# -------------------------------------------------------------

class TurnDetail(BaseModel):
    turn_id: str
    kind: Literal["user", "assistant", "thought", "edit", "shell", "read", "plan", "notice"]
    ts: str
    path: str | None = None
    instruction: str | None = None
    text: str | None = None
    command: str | None = None
    exit_code: int | None = None
    excerpt: str | None = None


class TurnsResponse(BaseModel):
    turns: list[TurnDetail] = Field(default_factory=list)


class CallerCalleeRef(BaseModel):
    id: str
    tier: Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"] = "EXTRACTED"
    via: str | None = None
    line: int | None = None
    in_graph: bool = True


class FileImportRef(BaseModel):
    module: str
    names: list[str] = Field(default_factory=list)
    context: str = "runtime"


class NearestTestedTest(BaseModel):
    id: str
    count: int = 0
    path: list[str] = Field(default_factory=list)


class NodeDetailTests(BaseModel):
    label: Literal["direct", "reached", "reached_uncertain", "none"]
    count: int = 0
    paths: list[list[str]] = Field(default_factory=list)
    nearest_tested: NearestTestedTest | None = None


class NodeDetailClass(BaseModel):
    id: str
    bases: list[str] = Field(default_factory=list)


class NodeDetailData(BaseModel):
    id: str
    kind: str
    path: str
    start_line: int
    end_line: int
    signature: str
    decorators: list[str] = Field(default_factory=list)
    is_async: bool = False
    is_public: bool = True
    doc: str | None = None
    class_: NodeDetailClass | None = Field(default=None, alias="class")


class NodeDetailResponse(BaseModel):
    node: NodeDetailData
    change: NodeChange | None = None
    source_head: str = ""
    diff: list[DiffHunk] = Field(default_factory=list)
    callers: list[CallerCalleeRef] = Field(default_factory=list)
    callees: list[CallerCalleeRef] = Field(default_factory=list)
    unresolved_calls: list[dict[str, Any]] = Field(default_factory=list)
    file_imports: list[FileImportRef] = Field(default_factory=list)
    file_imported_by: list[str] = Field(default_factory=list)
    tests: NodeDetailTests
    impact: list[ImpactHop] = Field(default_factory=list)


class MapCounts(BaseModel):
    folders: int
    files: int
    classes: int
    functions: int
    tests: int


class CodebaseMapResponse(BaseModel):
    repo: RepoRef
    map_sha: str
    columns: list[str] = ["id", "kind", "parent", "loc", "fan_in", "is_test"]
    nodes: list[list[Any]] = Field(default_factory=list)
    counts: MapCounts


class NodeEdgesResponse(BaseModel):
    id: str
    callers: list[dict[str, Any]] = Field(default_factory=list)
    callees: list[dict[str, Any]] = Field(default_factory=list)
    callers_total: int = 0
    callees_total: int = 0
