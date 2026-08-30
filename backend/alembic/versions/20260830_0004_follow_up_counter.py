"""Give the follow-up a counter.

Revision ID: 20260830_0004
Revises: 20260830_0003
Create Date: 2026-08-30

The section named the question that ends the LARP and then stopped, which is a
diagnosis rather than help. follow_up becomes {question, why, counter}, where
counter is {move, holds} or null when the entry honestly has no answer.

Stored documents are rewritten in place: the first line of the old list is the
question, the rest is the why, and no existing document gains a counter it did
not have. An editor or a regeneration supplies those.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0004"
down_revision: str | None = "20260830_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _revisions(connection):
    return connection.execute(
        sa.text("SELECT id, content FROM guide_revisions ORDER BY id")
    ).fetchall()


def _save(connection, revision_id, document) -> None:
    connection.execute(
        sa.text("UPDATE guide_revisions SET content = :content WHERE id = :id"),
        {"content": json.dumps(document), "id": revision_id},
    )


def upgrade() -> None:
    connection = op.get_bind()
    for revision_id, document in _revisions(connection):
        larp = ((document or {}).get("content") or {}).get("larp") or {}
        follow_up = larp.get("follow_up")
        if not isinstance(follow_up, list):
            continue
        lines = [line for line in follow_up if str(line).strip()]
        if not lines:
            continue
        larp["follow_up"] = {
            "question": lines[0],
            "why": "\n\n".join(lines[1:]) or lines[0],
            "counter": None,
        }
        _save(connection, revision_id, document)


def downgrade() -> None:
    connection = op.get_bind()
    for revision_id, document in _revisions(connection):
        larp = ((document or {}).get("content") or {}).get("larp") or {}
        follow_up = larp.get("follow_up")
        if not isinstance(follow_up, dict):
            continue
        lines = [follow_up.get("question", "")]
        why = follow_up.get("why") or ""
        lines.extend(part for part in why.split("\n\n") if part)
        larp["follow_up"] = [line for line in lines if line]
        _save(connection, revision_id, document)
