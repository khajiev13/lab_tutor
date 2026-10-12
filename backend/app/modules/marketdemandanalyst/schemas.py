"""Versioned market skill review boundary contracts."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.occupation_reference.schemas import ReleaseVersion, SocCode

JobSource = Literal["indeed", "linkedin", "headhunter"]
EvidenceSource = Literal["jobs", "onet"]


class SourceOutcome(BaseModel):
    status: Literal["idle", "loading", "success", "empty", "partial", "error"] = "idle"
    received_count: int = 0
    usable_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SkillCategory(BaseModel):
    category_id: str
    label: str


class SkillCandidate(BaseModel):
    candidate_id: UUID
    display_name: str
    category_id: str
    original_labels: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    job_metrics: dict[str, Any] = Field(default_factory=dict)
    onet_associations: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_reasons: list[str] = Field(default_factory=list)
    posting_support: Literal["supported", "missing"] = "missing"
    qualifying_posting_links: list[str] = Field(default_factory=list)


class RecommendationChange(BaseModel):
    candidate_id: UUID
    action: Literal["add", "remove"]
    reason: str


class RecommendationProposal(BaseModel):
    id: UUID
    candidate_revision: int
    base_selection_revision: int
    changes: list[RecommendationChange]


class PreviousCandidate(BaseModel):
    candidate_id: UUID
    display_name: str


class CandidateReconciliation(BaseModel):
    reconciliation_id: UUID
    candidate_id: UUID | None = None
    previous_candidate_ids: list[UUID] = Field(default_factory=list)
    reason: str
    previous_candidates: list[PreviousCandidate] = Field(default_factory=list)
    previous_selected_candidate_ids: list[UUID] = Field(default_factory=list)
    previous_excluded_candidate_ids: list[UUID] = Field(default_factory=list)
    resolved: bool = False


class AnalysisOccupation(BaseModel):
    soc_code: str
    title: str


class AnalysisMetadata(BaseModel):
    country: str | None = None
    job_sources: list[JobSource] = Field(default_factory=list)
    evidence_sources: list[EvidenceSource] = Field(default_factory=list)
    onet_release: str | None = None
    occupations: list[AnalysisOccupation] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ExecutionStatus(BaseModel):
    status: Literal["busy", "idle"]
    state_updated_at: datetime | None = None


class SkillReview(BaseModel):
    run_id: UUID | None = None
    analysis_metadata: AnalysisMetadata | None = None
    candidate_revision: int = 0
    selection_revision: int = 0
    categories: list[SkillCategory] = Field(default_factory=list)
    candidates: list[SkillCandidate] = Field(default_factory=list)
    selected_candidate_ids: list[UUID] = Field(default_factory=list)
    excluded_candidate_ids: list[UUID] = Field(default_factory=list)
    recommendations: list[RecommendationProposal] = Field(default_factory=list)
    reconciliations: list[CandidateReconciliation] = Field(default_factory=list)
    source_outcomes: dict[str, SourceOutcome] = Field(default_factory=dict)
    extraction_coverage: dict[str, Any] = Field(default_factory=dict)
    integration_review: dict[str, Any] | None = None
    publication_revision: int = 0
    approved_references: list[dict[str, Any]] = Field(default_factory=list)


class SkillReviewRevision(BaseModel):
    run_id: UUID
    expected_candidate_revision: int = Field(ge=0)
    expected_selection_revision: int = Field(ge=0)


class SkillReviewDraft(SkillReviewRevision):
    selected_candidate_ids: list[UUID]
    excluded_candidate_ids: list[UUID]
    resolved_reconciliation_ids: list[UUID] = Field(default_factory=list)


class JobSourceOption(BaseModel):
    id: JobSource
    label: str
    availability: Literal["available", "unsupported_country", "not_configured"]
    reason: str | None = None


def safe_provider_payload(value: Any, secret: str = "") -> Any:
    """Retain public fields, omitting credentials and non-JSON missing values."""
    import math

    if isinstance(value, dict):
        return {
            str(key): safe_provider_payload(item, secret)
            for key, item in value.items()
            if str(key).casefold().replace("-", "_")
            not in {
                "authorization",
                "proxy_authorization",
                "access_token",
                "refresh_token",
                "api_key",
                "token",
                "password",
                "secret",
                "headers",
                "request_headers",
            }
        }
    if isinstance(value, (list, tuple)):
        return [safe_provider_payload(item, secret) for item in value]
    if isinstance(value, str):
        return value.replace(secret, "[redacted]") if secret else value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class ProviderVacancy(BaseModel):
    provider: JobSource
    native_id: str | None = None
    title: str
    company: str = ""
    original_url: str = ""
    source_urls: list[str] = Field(default_factory=list)
    original_description: str = ""
    description_text: str = ""
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    location: str = ""
    skill_tags: list[str] = Field(default_factory=list)
    returned_dates: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    query_membership: list[str] = Field(default_factory=list)
    demand_identity: str | None = None

    @field_validator("raw_payload", "returned_dates")
    @classmethod
    def strip_credentials(cls, value):
        return safe_provider_payload(value)

    @field_validator("original_url")
    @classmethod
    def public_url(cls, value):
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Posting URL must be a public absolute HTTP(S) URL")
        if any(
            key in parsed.query.casefold()
            for key in ("access_token", "api_key", "authorization")
        ):
            raise ValueError("Posting URL must not contain credentials")
        return value


class FetchJobsResult(BaseModel):
    records: list[ProviderVacancy] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: dict[JobSource, SourceOutcome] = Field(default_factory=dict)


class VacancyEvidence(BaseModel):
    snapshot_id: UUID
    provider: JobSource
    native_id: str | None
    original_url: str
    title: str
    company: str
    description_text: str | None
    original_description: str | None
    raw_payload: dict[str, Any]
    retrieved_at: datetime
    status: str
    purged_at: datetime | None


class IntegrationApproval(SkillReviewRevision):
    review_digest: str = Field(min_length=64, max_length=64)
    approved_candidate_ids: list[UUID]


class IntegrationApprovalResult(BaseModel):
    review: SkillReview
    projection_status: Literal["pending", "projected", "error"]


# Contextual workspace requests carry identities, never client-supplied evidence.
InsightKind = Literal["common_sample", "occupation_difference", "shared_importance"]
WorkspaceMetric = Literal["frequency", "IM", "LV"]


class WorkspaceDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def strict_version(cls, value):
        if (
            isinstance(value, dict)
            and "version" in value
            and type(value["version"]) is not int
        ):
            raise ValueError("Context version must be an integer")
        return value

    @model_validator(mode="after")
    def bounded_json(self):
        if len(self.model_dump_json().encode("utf-8")) > 16 * 1024:
            raise ValueError("Workspace context exceeds 16 KiB")
        return self


class WorkspaceFilters(WorkspaceDTO):
    category_ids: list[str] = Field(default_factory=list, max_length=10)
    search: str = Field(default="", max_length=120)
    scope: Literal["all", "selected"] = "all"


class DescriptorChoice(WorkspaceDTO):
    candidate_id: UUID
    evidence_id: UUID


class RunReviewContext(WorkspaceDTO):
    kind: Literal["run_review"]
    version: Literal[1]
    intent: Literal["explain", "propose_selection"]
    run_id: UUID
    expected_candidate_revision: int = Field(ge=0, strict=True)
    expected_selection_revision: int = Field(ge=0, strict=True)
    view: Literal["overview", "demand_importance", "occupations", "data"]
    focused_candidate_id: UUID | None = None
    candidate_ids: list[UUID] = Field(default_factory=list, max_length=20)
    filters: WorkspaceFilters = Field(default_factory=WorkspaceFilters)
    occupation_codes: list[SocCode] = Field(default_factory=list, max_length=5)
    metric: WorkspaceMetric
    descriptor_choices: list[DescriptorChoice] = Field(
        default_factory=list, max_length=20
    )
    insight_kind: InsightKind | None = None
    has_unsaved_changes: bool = Field(default=False, strict=True)

    @field_validator("candidate_ids", "occupation_codes")
    @classmethod
    def distinct_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Context IDs must be distinct")
        return value


class OccupationReferenceContext(WorkspaceDTO):
    kind: Literal["occupation_reference"]
    version: Literal[1]
    intent: Literal["explain"]
    release: ReleaseVersion
    occupation_codes: list[SocCode] = Field(min_length=1, max_length=5)
    element_ids: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(
        default_factory=list, max_length=20
    )
    metric: Literal["IM", "LV"]

    @field_validator("occupation_codes", "element_ids")
    @classmethod
    def distinct_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Context IDs must be distinct")
        return value


WorkspaceContext = Annotated[
    RunReviewContext | OccupationReferenceContext, Field(discriminator="kind")
]


class PatternValue(BaseModel):
    candidate_id: str
    occupation_code: str | None = None
    value: float
    supporting_count: int | None = None
    assessed_count: int | None = None


class PatternObservation(BaseModel):
    kind: InsightKind
    candidate_ids: list[str]
    occupation_codes: list[str]
    descriptor_keys: list[tuple[str, str, str]]
    values: list[PatternValue]
    coverage: dict[str, Any]


class ResolvedContextMetadata(BaseModel):
    """Persistable facts only; source content stays in the detached model bundle."""

    kind: Literal["run_review", "occupation_reference"]
    version: Literal[1] = 1
    intent: Literal["explain", "propose_selection"]
    run_id: UUID | None = None
    candidate_revision: int | None = None
    selection_revision: int | None = None
    release: str | None = None
    view: str | None = None
    metric: WorkspaceMetric
    occupation_codes: list[str] = Field(default_factory=list)
    occupations: list[AnalysisOccupation] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    candidate_labels: dict[str, str] = Field(default_factory=dict)
    filters: WorkspaceFilters | None = None
    descriptor_choices: list[DescriptorChoice] = Field(default_factory=list)
    insight_kind: InsightKind | None = None
    matching_count: int
    included_count: int
    omitted_count: int
    evidence_included_count: int = 0
    evidence_omitted_count: int = 0
    facts: list[dict[str, Any]] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    notices: list[str] = Field(default_factory=list)


class ResolvedWorkspaceContext(BaseModel):
    request: WorkspaceContext
    intent: Literal["explain", "propose_selection"]
    revision: SkillReviewRevision | None = None
    model_bundle: dict[str, Any]
    history_metadata: ResolvedContextMetadata
