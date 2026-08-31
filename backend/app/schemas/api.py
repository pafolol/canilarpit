import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import (
    ApprovalStatus,
    EntryType,
    GuideStatus,
    GuideType,
    MediaKind,
    ResearchJobStatus,
    RevisionStatus,
    SubmissionStatus,
    UserRole,
    Verdict,
)
from app.schemas.content import GuideDocument
from app.services.text import normalize_text


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class CategorySummary(ORMModel):
    id: uuid.UUID
    slug: str
    title: str


class CategoryResponse(CategorySummary):
    description: str
    sort_order: int
    published_guide_count: int = 0


class LarpCard(BaseModel):
    """The verdict layer a card needs: what it is, whether it holds, and for how long."""

    entry_type: EntryType
    verdict: Verdict
    exposure_seconds: int | None
    unfalsifiable: bool
    flags: list[str]
    dek: str


class GuideListItem(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    summary: str
    guide_type: GuideType
    category: CategorySummary
    larp: LarpCard
    published_at: datetime | None


class GuidePage(BaseModel):
    items: list[GuideListItem]
    pagination: PaginationMeta


class SourceResponse(BaseModel):
    key: str
    title: str
    url: str
    publisher: str | None
    excerpt: str | None
    published_at: datetime | None
    verified_at: datetime | None


class MediaResponse(BaseModel):
    id: uuid.UUID
    link_id: uuid.UUID | None = None
    kind: MediaKind
    provider: str
    url: str | None
    source_page_url: str | None
    attribution: str | None
    license_name: str | None
    license_url: str | None
    alt_text: str
    width: int | None
    height: int | None
    metadata: dict[str, Any]
    approval_status: ApprovalStatus
    role: str | None = None
    caption: str | None = None
    sort_order: int | None = None


class GuideDetail(BaseModel):
    id: uuid.UUID
    revision_id: uuid.UUID
    revision_number: int
    slug: str
    title: str
    summary: str
    guide_type: GuideType
    category: CategorySummary
    larp: LarpCard
    content: dict[str, Any]
    aliases: list[str]
    sources: list[SourceResponse]
    media: list[MediaResponse]
    # Whoever suggested it, when a reader did.
    credit_name: str | None = None
    published_at: datetime | None
    last_verified_at: datetime | None


class TopicRequestCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=200)

    @field_validator("topic")
    @classmethod
    def valid_topic(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(normalize_text(cleaned)) < 2:
            raise ValueError("topic must contain at least two letters or numbers")
        return cleaned


class TopicRequestResponse(BaseModel):
    topic: str
    normalized_topic: str
    request_count: int | None = None
    recorded: bool
    matching_guide: GuideListItem | None = None


class UserResponse(ORMModel):
    id: uuid.UUID
    clerk_user_id: str
    email: str | None
    display_name: str | None
    avatar_url: str | None
    role: UserRole
    created_at: datetime


class HistoryItem(BaseModel):
    guide: GuideListItem
    first_viewed_at: datetime
    last_viewed_at: datetime
    view_count: int


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    pagination: PaginationMeta


class SavedGuideItem(BaseModel):
    guide: GuideListItem
    saved_at: datetime


class SavedGuidePage(BaseModel):
    items: list[SavedGuideItem]
    pagination: PaginationMeta


class SearchHistoryCreate(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    matched_guide_id: uuid.UUID | None = None

    @field_validator("query")
    @classmethod
    def valid_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not normalize_text(cleaned):
            raise ValueError("query must contain a letter or number")
        return cleaned


class SearchHistoryResponse(BaseModel):
    id: uuid.UUID
    query: str
    matched_guide_id: uuid.UUID | None
    created_at: datetime


class SearchHistoryPage(BaseModel):
    items: list[SearchHistoryResponse]
    pagination: PaginationMeta


class AdminRevisionResponse(BaseModel):
    id: uuid.UUID
    revision_number: int
    status: RevisionStatus
    content_hash: str
    document: GuideDocument
    media: list[MediaResponse]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class AdminGuideResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    summary: str
    guide_type: GuideType
    status: GuideStatus
    category: CategorySummary
    current_revision_id: uuid.UUID | None
    current_revision: AdminRevisionResponse | None = None
    draft_revision: AdminRevisionResponse | None = None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminGuidePage(BaseModel):
    items: list[AdminGuideResponse]
    pagination: PaginationMeta


class GuidePublishRequest(BaseModel):
    revision_id: uuid.UUID | None = None


class GuideValidationResponse(BaseModel):
    valid: bool
    content_hash: str
    document: GuideDocument


class MediaCreate(BaseModel):
    kind: MediaKind
    provider: str = Field(min_length=1, max_length=80)
    remote_url: AnyHttpUrl | None = None
    storage_key: str | None = Field(default=None, max_length=1000)
    source_page_url: AnyHttpUrl | None = None
    attribution: str | None = Field(default=None, max_length=2000)
    license_name: str | None = Field(default=None, max_length=120)
    license_url: AnyHttpUrl | None = None
    alt_text: str = Field(min_length=1, max_length=500)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT

    @model_validator(mode="after")
    def validate_location(self) -> "MediaCreate":
        if self.kind in {MediaKind.STOCK, MediaKind.EXTERNAL} and not self.remote_url:
            raise ValueError("stock and external media require remote_url")
        if self.kind in {MediaKind.GENERATED, MediaKind.UPLOADED} and not (
            self.storage_key or self.remote_url
        ):
            raise ValueError("generated and uploaded media require storage_key or remote_url")
        return self


class MediaApprovalUpdate(BaseModel):
    approval_status: ApprovalStatus


class GuideMediaLinkCreate(BaseModel):
    media_asset_id: uuid.UUID
    role: str = Field(default="gallery", min_length=1, max_length=80)
    caption: str | None = Field(default=None, max_length=2000)
    sort_order: int = Field(default=0, ge=0, le=10000)


class UploadPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"]
    kind: Literal["generated", "uploaded"] = "uploaded"


class UploadPresignResponse(BaseModel):
    upload_url: str
    storage_key: str
    public_url: str | None
    required_headers: dict[str, str]


class ResearchJobCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    guide_type: GuideType | None = None
    instructions: str | None = Field(default=None, max_length=5000)
    provider_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def valid_topic(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(normalize_text(cleaned)) < 2:
            raise ValueError("topic must contain at least two letters or numbers")
        return cleaned


class ResearchJobResponse(ORMModel):
    id: uuid.UUID
    topic: str
    normalized_topic: str
    guide_type: GuideType | None
    status: ResearchJobStatus
    instructions: str | None
    provider_config: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    attempt_count: int
    estimated_cost_micros: int
    created_guide_id: uuid.UUID | None = None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearchJobPage(BaseModel):
    items: list[ResearchJobResponse]
    pagination: PaginationMeta


class ResearchJobComplete(BaseModel):
    status: Literal["review", "completed", "failed"]
    result: dict[str, Any] | None = None
    error_message: str | None = Field(default=None, max_length=5000)
    estimated_cost_micros: int = Field(default=0, ge=0)


class TopicRequestAdminItem(ORMModel):
    id: uuid.UUID
    topic: str
    normalized_topic: str
    request_count: int
    first_requested_at: datetime
    last_requested_at: datetime


class TopicRequestAdminPage(BaseModel):
    items: list[TopicRequestAdminItem]
    pagination: PaginationMeta


class GuideGenerateRequest(BaseModel):
    """One click in the admin panel: a topic in, a reviewable draft guide out."""

    topic: str = Field(min_length=2, max_length=200)
    guide_type: GuideType | None = None
    entry_type: EntryType | None = None
    category_slug: str | None = Field(default=None, max_length=80)
    instructions: str | None = Field(default=None, max_length=5000)
    attach_images: bool = True

    @field_validator("topic")
    @classmethod
    def valid_topic(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(normalize_text(cleaned)) < 2:
            raise ValueError("topic must contain at least two letters or numbers")
        return cleaned


class GuideRegenerateRequest(BaseModel):
    """Rewrite an existing guide in place.

    Topic, type and category come from the guide itself; only the steering is
    worth asking for. The result is always a draft on the same guide.
    """

    instructions: str | None = Field(default=None, max_length=5000)
    attach_images: bool = True
    replace_images: bool = False


class GuideGenerateResponse(BaseModel):
    job: ResearchJobResponse
    guide: AdminGuideResponse | None = None
    attached_media: list[MediaResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ImageCandidate(BaseModel):
    """One image a provider offered, with the rights information it came with."""

    provider: str
    remote_url: str
    preview_url: str | None = None
    source_page_url: str | None = None
    attribution: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    alt_text: str
    width: int | None = None
    height: int | None = None
    subject: str | None = None
    # True for promotional stills and cover art: usable editorially with credit,
    # but the rights belong to whoever owns the film, show or photograph.
    editorial_only: bool = False


class ImageProviderInfo(BaseModel):
    id: str
    title: str
    subjects: str
    configured: bool
    requires_key: bool
    editorial_only: bool


class ImageSearchResponse(BaseModel):
    query: str
    provider: str
    results: list[ImageCandidate]
    warnings: list[str] = Field(default_factory=list)


class AiStatusResponse(BaseModel):
    """What the admin panel needs to know before it offers the generate button."""

    text_provider: str
    text_model: str
    text_configured: bool
    image_providers: list[ImageProviderInfo]
    images_configured: bool
    storage_configured: bool


class SiteConfigResponse(BaseModel):
    """Public, secret-free. It tells the frontend which sign-in paths are available."""

    app_env: str
    dev_auth_bypass: bool
    clerk_configured: bool


class SubmissionFormToken(BaseModel):
    """Handed out with the form and required back with the submission."""

    token: str
    min_seconds: float
    expires_in: int


class SubmissionCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    notes: str = Field(min_length=1, max_length=4000)
    guide_type: GuideType | None = None
    entry_type: EntryType | None = None
    category_slug: str | None = Field(default=None, max_length=80)
    suggested_category: str | None = Field(default=None, max_length=80)
    credit_name: str | None = Field(default=None, max_length=80)
    token: str = Field(min_length=1, max_length=300)
    # Hidden in the layout and labelled "leave this empty". Browsers do; bots do not.
    website: str | None = Field(default=None, max_length=200)

    @field_validator("topic")
    @classmethod
    def valid_topic(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(normalize_text(cleaned)) < 2:
            raise ValueError("topic must contain at least two letters or numbers")
        return cleaned

    @field_validator("credit_name", "suggested_category")
    @classmethod
    def tidy_optional(cls, value: str | None) -> str | None:
        cleaned = " ".join(value.split()) if value else None
        return cleaned or None

    @model_validator(mode="after")
    def one_category_choice(self) -> "SubmissionCreate":
        if self.category_slug and self.suggested_category:
            raise ValueError("choose an existing category or suggest one, not both")
        return self


class SubmissionReceipt(BaseModel):
    """What the sender is told. Deliberately thin: no ids they could poll."""

    received: bool
    topic: str
    message: str
    matching_guide: GuideListItem | None = None


class SubmissionAdminItem(ORMModel):
    id: uuid.UUID
    topic: str
    normalized_topic: str
    notes: str
    guide_type: GuideType | None
    entry_type: EntryType | None
    category: CategorySummary | None = None
    suggested_category: str | None
    credit_name: str | None
    status: SubmissionStatus
    screening: dict[str, Any] | None
    review_notes: str | None
    created_guide_id: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    # Anonymous, and shown only so an editor can block a persistent nuisance.
    client_hash: str


class SubmissionAdminPage(BaseModel):
    items: list[SubmissionAdminItem]
    pagination: PaginationMeta


class SubmissionDecision(BaseModel):
    review_notes: str | None = Field(default=None, max_length=2000)
    block_client: bool = False


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=1000)
    sort_order: int = Field(default=500, ge=0, le=10000)


class CategoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None
