"""Password sign-in and server-side sessions, replacing the Clerk integration.

`clerk_user_id` becomes `external_id`: the column still identifies the accounts
that do not sign in with a password - the seeder, the local development
identity, the test fixtures - but it is nullable now, because a real editor has
an email address and a password instead.

Nothing is dropped that holds content. Existing rows keep their identifier under
the new name and simply have no password, which means they cannot be signed in
to from the sign-in form. That is the intended outcome: `system:seed` was never
a person.

The email column gains a unique constraint, since it is the login handle now.
Any duplicate addresses have to be resolved before this will apply, and the
upgrade says so rather than failing on a constraint violation.

Revision ID: 20260831_0010
Revises: 20260830_0009
"""

import sqlalchemy as sa

from alembic import op

revision = "20260831_0010"
down_revision = "20260830_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # Fail with an explanation rather than on a constraint. Two accounts sharing
    # an address is harmless while nobody signs in with one, and fatal after.
    duplicates = connection.execute(
        sa.text(
            "SELECT lower(email) AS address, count(*) AS n FROM users "
            "WHERE email IS NOT NULL GROUP BY lower(email) HAVING count(*) > 1"
        )
    ).all()
    if duplicates:
        listed = ", ".join(f"{row.address} ({row.n} rows)" for row in duplicates)
        raise RuntimeError(
            "Email is about to become the login handle and must be unique, but these "
            f"addresses appear more than once: {listed}. Resolve them, then migrate."
        )

    op.alter_column("users", "clerk_user_id", new_column_name="external_id")
    op.alter_column("users", "external_id", existing_type=sa.String(255), nullable=True)
    op.drop_column("users", "clerk_updated_at")

    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("password_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Stored lowered from here on, so the unique index is the whole comparison.
    connection.execute(sa.text("UPDATE users SET email = lower(email) WHERE email IS NOT NULL"))
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The SHA-256 of the cookie, never the cookie. A copy of this table is
        # not a set of working sessions.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(400), nullable=True),
        sa.Column("client_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_index("ix_sessions_client_hash", "sessions", ["client_hash"])

    # The Clerk webhook is gone, so its replay-guard table has nothing to guard.
    op.drop_table("webhook_events")


def downgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_webhook_events_provider_id"),
    )

    op.drop_index("ix_sessions_client_hash", table_name="sessions")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "password_updated_at")
    op.drop_column("users", "password_hash")
    op.add_column(
        "users", sa.Column("clerk_updated_at", sa.DateTime(timezone=True), nullable=True)
    )

    # A row with no external id cannot go back to a schema that requires one.
    op.get_bind().execute(
        sa.text("DELETE FROM users WHERE external_id IS NULL")
    )
    op.alter_column("users", "external_id", existing_type=sa.String(255), nullable=False)
    op.alter_column("users", "external_id", new_column_name="clerk_user_id")
