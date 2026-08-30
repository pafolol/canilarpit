"""Rename the not_really verdict to talk_only.

Revision ID: 20260830_0003
Revises: 20260830_0002
Create Date: 2026-08-30

"NOT REALLY" read as a refusal. The finding it actually described - you can
hold the conversation, you cannot do the thing - is useful and encouraging, so
it is now TALK ONLY. DONT stays, for claims that put someone at risk.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260830_0003"
down_revision: str | None = "20260830_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "verdict IN ('yes', 'kinda', 'not_really', 'dont')"
NEW = "verdict IN ('yes', 'kinda', 'talk_only', 'dont')"


def upgrade() -> None:
    op.drop_constraint("verdict", "guides", type_="check")
    op.execute("UPDATE guides SET verdict = 'talk_only' WHERE verdict = 'not_really'")
    op.create_check_constraint("verdict", "guides", NEW)

    # The verdict also lives inside every stored revision document.
    op.execute(
        """
        UPDATE guide_revisions
        SET content = jsonb_set(content, '{content,larp,verdict}', '"talk_only"')
        WHERE content #>> '{content,larp,verdict}' = 'not_really'
        """
    )


def downgrade() -> None:
    op.drop_constraint("verdict", "guides", type_="check")
    op.execute("UPDATE guides SET verdict = 'not_really' WHERE verdict = 'talk_only'")
    op.create_check_constraint("verdict", "guides", OLD)
    op.execute(
        """
        UPDATE guide_revisions
        SET content = jsonb_set(content, '{content,larp,verdict}', '"not_really"')
        WHERE content #>> '{content,larp,verdict}' = 'talk_only'
        """
    )
