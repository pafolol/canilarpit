"""Widen guide_type beyond anime, lifestyle and general.

Revision ID: 20260830_0006
Revises: 20260830_0005
Create Date: 2026-08-30

"general" was holding seven of fifteen guides and handing all of them the same
two fields. screen, craft and profession give a film, a practised skill and a
job title the shape each actually needs.

Only the constraints move here. Existing documents keep the type they have,
because a general document has none of the fields a profession document
requires; retyping one is a rewrite, not a data migration.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260830_0006"
down_revision: str | None = "20260830_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "('anime', 'lifestyle', 'general')"
NEW = "('anime', 'screen', 'lifestyle', 'craft', 'profession', 'general')"


def upgrade() -> None:
    op.drop_constraint("guide_type", "guides", type_="check")
    op.create_check_constraint("guide_type", "guides", f"guide_type IN {NEW}")
    op.drop_constraint("research_guide_type", "research_jobs", type_="check")
    op.create_check_constraint(
        "research_guide_type", "research_jobs", f"guide_type IN {NEW}"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM research_jobs WHERE guide_type NOT IN {OLD}")
    op.drop_constraint("research_guide_type", "research_jobs", type_="check")
    op.create_check_constraint(
        "research_guide_type", "research_jobs", f"guide_type IN {OLD}"
    )
    op.drop_constraint("guide_type", "guides", type_="check")
    op.create_check_constraint("guide_type", "guides", f"guide_type IN {OLD}")
