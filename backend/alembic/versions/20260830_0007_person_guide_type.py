"""Add the person guide type.

Revision ID: 20260830_0007
Revises: 20260830_0006
Create Date: 2026-08-30

A named individual whose work people claim to know: the director, the theorist,
the musician carried unread. Its distinguishing field is `misattributions` - the
quote they never said, the film they disowned - because knowing one of those
carries further than knowing the bibliography.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260830_0007"
down_revision: str | None = "20260830_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "('anime', 'screen', 'lifestyle', 'craft', 'profession', 'general')"
NEW = "('anime', 'screen', 'lifestyle', 'person', 'craft', 'profession', 'general')"


def _swap(new: str) -> None:
    op.drop_constraint("guide_type", "guides", type_="check")
    op.create_check_constraint("guide_type", "guides", f"guide_type IN {new}")
    op.drop_constraint("research_guide_type", "research_jobs", type_="check")
    op.create_check_constraint("research_guide_type", "research_jobs", f"guide_type IN {new}")


def upgrade() -> None:
    _swap(NEW)


def downgrade() -> None:
    op.execute(f"DELETE FROM research_jobs WHERE guide_type NOT IN {OLD}")
    _swap(OLD)
