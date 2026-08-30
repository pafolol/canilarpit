import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(enum.StrEnum):
    MEMBER = "member"
    EDITOR = "editor"
    ADMIN = "admin"


class GuideStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class GuideType(enum.StrEnum):
    ANIME = "anime"
    LIFESTYLE = "lifestyle"
    GENERAL = "general"


class EntryType(enum.StrEnum):
    """The axis a guide sits on: a place you go, a thing you like, a thing you claim to be."""

    SCENE = "scene"
    TASTE = "taste"
    ROLE = "role"


class Verdict(enum.StrEnum):
    """How far the LARP holds, and what part of it holds.

    Three of the four are encouraging on purpose: the site exists to help, and
    "you can hold the conversation but not do the thing" is a useful finding,
    not a refusal. DONT is reserved for claims that put someone at risk.
    """

    YES = "yes"
    KINDA = "kinda"
    TALK_ONLY = "talk_only"
    DONT = "dont"


class RevisionStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


class MediaKind(enum.StrEnum):
    STOCK = "stock"
    EXTERNAL = "external"
    GENERATED = "generated"
    UPLOADED = "uploaded"


class ApprovalStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    BROKEN = "broken"


class ResearchJobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def enum_type(enum_class: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda values: [item.value for item in values],
        validate_strings=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    clerk_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[UserRole] = mapped_column(
        enum_type(UserRole, "user_role"), default=UserRole.MEMBER, server_default="member"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Guide(TimestampMixin, Base):
    __tablename__ = "guides"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    summary: Mapped[str] = mapped_column(Text)
    guide_type: Mapped[GuideType] = mapped_column(enum_type(GuideType, "guide_type"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[GuideStatus] = mapped_column(
        enum_type(GuideStatus, "guide_status"),
        default=GuideStatus.DRAFT,
        server_default="draft",
        index=True,
    )
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "guide_revisions.id",
            name="fk_guides_current_revision_id_guide_revisions",
            use_alter=True,
            ondelete="SET NULL",
        ),
    )
    entry_type: Mapped[EntryType] = mapped_column(
        enum_type(EntryType, "entry_type"),
        default=EntryType.TASTE,
        server_default="taste",
        index=True,
    )
    verdict: Mapped[Verdict] = mapped_column(
        enum_type(Verdict, "verdict"),
        default=Verdict.KINDA,
        server_default="kinda",
        index=True,
    )
    exposure_seconds: Mapped[int | None] = mapped_column(Integer)
    unfalsifiable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    flags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    dek: Mapped[str] = mapped_column(Text, default="", server_default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuideRevision(TimestampMixin, Base):
    __tablename__ = "guide_revisions"
    __table_args__ = (
        UniqueConstraint("guide_id", "revision_number"),
        Index("ix_guide_revisions_guide_status", "guide_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    guide_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("guides.id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[RevisionStatus] = mapped_column(
        enum_type(RevisionStatus, "revision_status"),
        default=RevisionStatus.DRAFT,
        server_default="draft",
        index=True,
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    source_commit_sha: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuideAlias(Base):
    __tablename__ = "guide_aliases"
    __table_args__ = (UniqueConstraint("guide_id", "normalized_alias"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    guide_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("guides.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(200))
    normalized_alias: Mapped[str] = mapped_column(String(200), index=True)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("guide_revision_id", "source_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    guide_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("guide_revisions.id", ondelete="CASCADE"), index=True
    )
    source_key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(160))
    excerpt: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[MediaKind] = mapped_column(enum_type(MediaKind, "media_kind"), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    remote_url: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    source_page_url: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    license_name: Mapped[str | None] = mapped_column(String(120))
    license_url: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str] = mapped_column(String(500))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        enum_type(ApprovalStatus, "approval_status"),
        default=ApprovalStatus.DRAFT,
        server_default="draft",
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class GuideMedia(Base):
    __tablename__ = "guide_media"
    __table_args__ = (
        UniqueConstraint("guide_revision_id", "media_asset_id", "role"),
        Index("ix_guide_media_revision_order", "guide_revision_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    guide_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("guide_revisions.id", ondelete="CASCADE"), index=True
    )
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(80), default="gallery", server_default="gallery")
    caption: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class SavedGuide(Base):
    __tablename__ = "saved_guides"
    __table_args__ = (UniqueConstraint("user_id", "guide_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("guides.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GuideHistory(Base):
    __tablename__ = "guide_history"
    __table_args__ = (UniqueConstraint("user_id", "guide_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    guide_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("guides.id", ondelete="CASCADE"), index=True
    )
    first_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    view_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class SearchHistory(Base):
    __tablename__ = "search_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(String(200))
    normalized_query: Mapped[str] = mapped_column(String(200), index=True)
    matched_guide_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("guides.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class TopicRequest(Base):
    __tablename__ = "topic_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(200))
    normalized_topic: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    request_count: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")
    first_requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    last_requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class ResearchJob(TimestampMixin, Base):
    __tablename__ = "research_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(200))
    normalized_topic: Mapped[str] = mapped_column(String(200), index=True)
    guide_type: Mapped[GuideType | None] = mapped_column(
        enum_type(GuideType, "research_guide_type")
    )
    status: Mapped[ResearchJobStatus] = mapped_column(
        enum_type(ResearchJobStatus, "research_job_status"),
        default=ResearchJobStatus.QUEUED,
        server_default="queued",
        index=True,
    )
    instructions: Mapped[str | None] = mapped_column(Text)
    provider_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    estimated_cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_guide_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("guides.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50))
    external_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(120))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("provider", "external_event_id"),)
