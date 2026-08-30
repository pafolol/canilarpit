"""LARP verdict columns on guides and a generated-guide link on research jobs.

Revision ID: 20260830_0002
Revises: 20260823_0001
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260830_0002"
down_revision: str | None = "20260823_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Denormalized from the published revision document so guide cards and the
    # verdict/type filters never have to open the revision JSONB.
    op.add_column(
        "guides",
        sa.Column("entry_type", sa.String(32), server_default="taste", nullable=False),
    )
    op.add_column(
        "guides",
        sa.Column("verdict", sa.String(32), server_default="kinda", nullable=False),
    )
    op.add_column("guides", sa.Column("exposure_seconds", sa.Integer()))
    op.add_column(
        "guides",
        sa.Column("unfalsifiable", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "guides",
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column("guides", sa.Column("dek", sa.Text(), server_default="", nullable=False))
    op.create_check_constraint(
        "entry_type", "guides", "entry_type IN ('scene', 'taste', 'role')"
    )
    op.create_check_constraint(
        "verdict", "guides", "verdict IN ('yes', 'kinda', 'not_really', 'dont')"
    )
    op.create_index("ix_guides_entry_type", "guides", ["entry_type"])
    op.create_index("ix_guides_verdict", "guides", ["verdict"])

    op.add_column(
        "research_jobs",
        sa.Column(
            "created_guide_id",
            sa.Uuid(),
            sa.ForeignKey("guides.id", ondelete="SET NULL"),
        ),
    )


def downgrade() -> None:
    op.drop_column("research_jobs", "created_guide_id")
    op.drop_index("ix_guides_verdict", table_name="guides")
    op.drop_index("ix_guides_entry_type", table_name="guides")
    op.drop_constraint("verdict", "guides", type_="check")
    op.drop_constraint("entry_type", "guides", type_="check")
    op.drop_column("guides", "dek")
    op.drop_column("guides", "flags")
    op.drop_column("guides", "unfalsifiable")
    op.drop_column("guides", "exposure_seconds")
    op.drop_column("guides", "verdict")
    op.drop_column("guides", "entry_type")
