"""Counting: hours to learn, views, and who is here now.

Revision ID: 20260830_0009
Revises: 20260830_0008
Create Date: 2026-08-30

Three things the site could not say before.

`guides.learn_hours` is denormalised out of the published document so
`/just-learn-it` can sort in SQL rather than opening every revision. It is
backfilled here, so the page has data the moment it ships.

`guides.view_count` plus `guide_views` count readers. The rows exist so the
count can be deduped per client per guide; without that the number is a refresh
count, not a readership.

`presence` is one row per anonymous client, in the database rather than in
memory so the number survives a restart and stays right under more than one
worker. Both new tables key on the same HMAC the submission form uses: no raw
address is stored.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0009"
down_revision: str | None = "20260830_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("guides", sa.Column("learn_hours", sa.Integer()))
    op.add_column(
        "guides",
        sa.Column("view_count", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.create_index("ix_guides_view_count", "guides", ["view_count"])

    op.create_table(
        "guide_views",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "guide_id",
            sa.Uuid(),
            sa.ForeignKey("guides.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_hash", sa.String(64), nullable=False),
        sa.Column(
            "viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_guide_views_guide_id", "guide_views", ["guide_id"])
    op.create_index("ix_guide_views_client_hash", "guide_views", ["client_hash"])
    op.create_index("ix_guide_views_viewed_at", "guide_views", ["viewed_at"])
    # The dedupe query reads exactly this: one guide, one client, recently.
    op.create_index(
        "ix_guide_views_guide_client_seen",
        "guide_views",
        ["guide_id", "client_hash", "viewed_at"],
    )

    op.create_table(
        "presence",
        sa.Column("client_hash", sa.String(64), primary_key=True),
        sa.Column(
            "last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_presence_last_seen", "presence", ["last_seen"])

    # Backfill from whichever revision is live, so the page is not empty on day one.
    op.execute(
        sa.text(
            """
            UPDATE guides
               SET learn_hours = (
                     (r.content -> 'content' -> 'larp' -> 'learn' ->> 'hours')::int
                   )
              FROM guide_revisions AS r
             WHERE r.id = guides.current_revision_id
               AND jsonb_typeof(r.content -> 'content' -> 'larp' -> 'learn' -> 'hours')
                   = 'number'
            """
        )
    )


def downgrade() -> None:
    op.drop_table("presence")
    op.drop_table("guide_views")
    op.drop_index("ix_guides_view_count", table_name="guides")
    op.drop_column("guides", "view_count")
    op.drop_column("guides", "learn_hours")
