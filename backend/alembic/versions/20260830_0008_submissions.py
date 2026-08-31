"""Reader submissions, with the anti-abuse columns they need.

Revision ID: 20260830_0008
Revises: 20260830_0007
Create Date: 2026-08-30

A reader who searches for something we have not written can now send a guide
suggestion rather than only a topic name.

`client_hash` is an HMAC of the address and user agent with a server secret. No
raw address is stored: it is enough to rate limit and to block somebody who will
not stop, and useless for identifying anyone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260830_0008"
down_revision: str | None = "20260830_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GUIDE_TYPES = "('anime', 'screen', 'lifestyle', 'person', 'craft', 'profession', 'general')"
ENTRY_TYPES = "('scene', 'taste', 'role')"
STATUSES = "('pending', 'screened', 'drafted', 'accepted', 'rejected', 'spam')"


def upgrade() -> None:
    op.add_column("guides", sa.Column("credit_name", sa.String(80)))

    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("normalized_topic", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("guide_type", sa.String(32)),
        sa.Column("entry_type", sa.String(32)),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("suggested_category", sa.String(80)),
        sa.Column("credit_name", sa.String(80)),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("screening", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("review_notes", sa.Text()),
        sa.Column("created_guide_id", sa.Uuid(), sa.ForeignKey("guides.id", ondelete="SET NULL")),
        sa.Column(
            "reviewed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("client_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"status IN {STATUSES}", name="submission_status"),
        sa.CheckConstraint(
            f"guide_type IS NULL OR guide_type IN {GUIDE_TYPES}", name="submission_guide_type"
        ),
        sa.CheckConstraint(
            f"entry_type IS NULL OR entry_type IN {ENTRY_TYPES}", name="submission_entry_type"
        ),
    )
    op.create_index("ix_submissions_normalized_topic", "submissions", ["normalized_topic"])
    op.create_index("ix_submissions_status", "submissions", ["status"])
    op.create_index("ix_submissions_created_at", "submissions", ["created_at"])
    op.create_index("ix_submissions_client_hash", "submissions", ["client_hash"])
    op.create_index("ix_submissions_status_created", "submissions", ["status", "created_at"])
    op.create_index("ix_submissions_client", "submissions", ["client_hash", "created_at"])

    op.create_table(
        "blocked_clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "blocked_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("client_hash"),
    )
    op.create_index("ix_blocked_clients_client_hash", "blocked_clients", ["client_hash"])


def downgrade() -> None:
    op.drop_table("blocked_clients")
    op.drop_table("submissions")
    op.drop_column("guides", "credit_name")
