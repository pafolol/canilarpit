"""Retire the TMDB image provider.

Revision ID: 20260830_0005
Revises: 20260830_0004
Create Date: 2026-08-30

TMDB licenses its API for personal use and charges for commercial use, so it is
out of the registry. Stored image briefs that named it fall back to "auto",
which routes by category: series to TVmaze, film to Commons.

fanart.tv stays. It no longer resolves ids through TMDB - TVmaze supplies
TheTVDB id for television, Wikidata supplies the IMDb id for film.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0005"
down_revision: str | None = "20260830_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rewrite(connection, replace_with: str, matching: str) -> int:
    rows = connection.execute(
        sa.text("SELECT id, content FROM guide_revisions ORDER BY id")
    ).fetchall()
    changed = 0
    for revision_id, document in rows:
        brief = ((document or {}).get("content") or {}).get("image_brief") or []
        touched = False
        for item in brief:
            if item.get("provider") == matching:
                item["provider"] = replace_with
                touched = True
        if touched:
            connection.execute(
                sa.text("UPDATE guide_revisions SET content = :content WHERE id = :id"),
                {"content": json.dumps(document), "id": revision_id},
            )
            changed += 1
    return changed


def upgrade() -> None:
    _rewrite(op.get_bind(), replace_with="auto", matching="tmdb")


def downgrade() -> None:
    # "auto" is a legitimate choice in its own right, so this cannot be undone
    # without guessing which entries were originally TMDB's.
    pass
