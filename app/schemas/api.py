import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import (
    ApprovalStatus,
    GuideStatus,
    GuideType,
    MediaKind,
    ResearchJobStatus,
    RevisionStatus,
    UserRole,
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


class GuideListItem(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    summary: str
    guide_type: GuideType
    category: CategorySummary
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
    content: dict[str, Any]
    aliases: list[str]
    sources: list[SourceResponse]
    media: list[MediaResponse]
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
