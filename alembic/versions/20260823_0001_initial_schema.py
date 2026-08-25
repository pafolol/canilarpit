"""Initial PostgreSQL schema.

Revision ID: 20260823_0001
Revises: None
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260823_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("clerk_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(120)),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("clerk_updated_at", sa.DateTime(timezone=True)),
        sa.Column("role", sa.String(32), server_default="member", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("role IN ('member', 'editor', 'admin')", name="user_role"),
        sa.UniqueConstraint("clerk_user_id"),
    )
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"])

    op.create_table(
        "guides",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("guide_type", sa.String(32), nullable=False),
        sa.Column(
            "category_id",
            sa.Uuid(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("current_revision_id", sa.Uuid()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("guide_type IN ('anime', 'lifestyle', 'general')", name="guide_type"),
        sa.CheckConstraint(
            "status IN ('draft', 'in_review', 'published', 'archived')",
            name="guide_status",
        ),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_guides_slug", "guides", ["slug"])
    op.create_index("ix_guides_title", "guides", ["title"])
    op.create_index("ix_guides_guide_type", "guides", ["guide_type"])
    op.create_index("ix_guides_category_id", "guides", ["category_id"])
    op.create_index("ix_guides_status", "guides", ["status"])
    op.create_index("ix_guides_published_at", "guides", ["published_at"])
    op.execute("CREATE INDEX ix_guides_title_trgm ON guides USING gin (title gin_trgm_ops)")

    op.create_table(
        "guide_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "guide_id", sa.Uuid(), sa.ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("author_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("source_commit_sha", sa.String(64)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('draft', 'in_review', 'published', 'superseded')",
            name="revision_status",
        ),
        sa.UniqueConstraint("guide_id", "revision_number"),
    )
    op.create_index("ix_guide_revisions_guide_id", "guide_revisions", ["guide_id"])
    op.create_index("ix_guide_revisions_content_hash", "guide_revisions", ["content_hash"])
    op.create_index("ix_guide_revisions_status", "guide_revisions", ["status"])
    op.create_index("ix_guide_revisions_guide_status", "guide_revisions", ["guide_id", "status"])
    op.create_foreign_key(
        "fk_guides_current_revision_id_guide_revisions",
        "guides",
        "guide_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "guide_aliases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "guide_id", sa.Uuid(), sa.ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("alias", sa.String(200), nullable=False),
        sa.Column("normalized_alias", sa.String(200), nullable=False),
        sa.UniqueConstraint("guide_id", "normalized_alias"),
    )
    op.create_index("ix_guide_aliases_guide_id", "guide_aliases", ["guide_id"])
    op.create_index("ix_guide_aliases_normalized_alias", "guide_aliases", ["normalized_alias"])

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "guide_revision_id",
            sa.Uuid(),
            sa.ForeignKey("guide_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_key", sa.String(80), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("publisher", sa.String(160)),
        sa.Column("excerpt", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("guide_revision_id", "source_key"),
    )
    op.create_index("ix_sources_guide_revision_id", "sources", ["guide_revision_id"])

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("remote_url", sa.Text()),
        sa.Column("storage_key", sa.Text()),
        sa.Column("source_page_url", sa.Text()),
        sa.Column("attribution", sa.Text()),
        sa.Column("license_name", sa.String(120)),
        sa.Column("license_url", sa.Text()),
        sa.Column("alt_text", sa.String(500), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("approval_status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *timestamps(),
        sa.CheckConstraint(
            "kind IN ('stock', 'external', 'generated', 'uploaded')", name="media_kind"
        ),
        sa.CheckConstraint(
            "approval_status IN ('draft', 'approved', 'rejected', 'broken')",
            name="approval_status",
        ),
    )
    op.create_index("ix_media_assets_kind", "media_assets", ["kind"])
    op.create_index("ix_media_assets_approval_status", "media_assets", ["approval_status"])

    op.create_table(
        "guide_media",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "guide_revision_id",
            sa.Uuid(),
            sa.ForeignKey("guide_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_asset_id",
            sa.Uuid(),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(80), server_default="gallery", nullable=False),
        sa.Column("caption", sa.Text()),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.UniqueConstraint("guide_revision_id", "media_asset_id", "role"),
    )
    op.create_index("ix_guide_media_guide_revision_id", "guide_media", ["guide_revision_id"])
    op.create_index("ix_guide_media_media_asset_id", "guide_media", ["media_asset_id"])
    op.create_index(
        "ix_guide_media_revision_order", "guide_media", ["guide_revision_id", "sort_order"]
    )

    op.create_table(
        "saved_guides",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "guide_id", sa.Uuid(), sa.ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "guide_id"),
    )
    op.create_index("ix_saved_guides_user_id", "saved_guides", ["user_id"])
    op.create_index("ix_saved_guides_guide_id", "saved_guides", ["guide_id"])

    op.create_table(
        "guide_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "guide_id", sa.Uuid(), sa.ForeignKey("guides.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "first_viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("view_count", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("user_id", "guide_id"),
    )
    op.create_index("ix_guide_history_user_id", "guide_history", ["user_id"])
    op.create_index("ix_guide_history_guide_id", "guide_history", ["guide_id"])
    op.create_index("ix_guide_history_last_viewed_at", "guide_history", ["last_viewed_at"])

    op.create_table(
        "search_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("query", sa.String(200), nullable=False),
        sa.Column("normalized_query", sa.String(200), nullable=False),
        sa.Column("matched_guide_id", sa.Uuid(), sa.ForeignKey("guides.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_search_history_user_id", "search_history", ["user_id"])
    op.create_index("ix_search_history_normalized_query", "search_history", ["normalized_query"])
    op.create_index("ix_search_history_created_at", "search_history", ["created_at"])

    op.create_table(
        "topic_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("normalized_topic", sa.String(200), nullable=False),
        sa.Column("request_count", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column(
            "first_requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_requested_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.UniqueConstraint("normalized_topic"),
    )
    op.create_index("ix_topic_requests_normalized_topic", "topic_requests", ["normalized_topic"])
    op.create_index("ix_topic_requests_last_requested_at", "topic_requests", ["last_requested_at"])

    op.create_table(
        "research_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("normalized_topic", sa.String(200), nullable=False),
        sa.Column("guide_type", sa.String(32)),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("instructions", sa.Text()),
        sa.Column(
            "provider_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("error_message", sa.Text()),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_micros", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "requested_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "guide_type IS NULL OR guide_type IN ('anime', 'lifestyle', 'general')",
            name="research_guide_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'review', 'completed', 'failed', 'cancelled')",
            name="research_job_status",
        ),
    )
    op.create_index("ix_research_jobs_normalized_topic", "research_jobs", ["normalized_topic"])
    op.create_index("ix_research_jobs_status", "research_jobs", ["status"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("provider", "external_event_id"),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("audit_log")
    op.drop_table("research_jobs")
    op.drop_table("topic_requests")
    op.drop_table("search_history")
    op.drop_table("guide_history")
    op.drop_table("saved_guides")
    op.drop_table("guide_media")
    op.drop_table("media_assets")
    op.drop_table("sources")
    op.drop_table("guide_aliases")
    op.drop_constraint(
        "fk_guides_current_revision_id_guide_revisions", "guides", type_="foreignkey"
    )
    op.drop_table("guide_revisions")
    op.drop_table("guides")
    op.drop_table("categories")
    op.drop_table("users")
