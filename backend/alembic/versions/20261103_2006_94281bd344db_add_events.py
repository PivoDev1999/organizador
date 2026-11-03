"""add events

Revision ID: 94281bd344db
Revises: b0e9e518b85c
Create Date: 2026-11-03 20:06:05.225444

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "94281bd344db"
down_revision: str | None = "b0e9e518b85c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen on purpose: a migration must not import the current models.
FILE_ENTITY_TYPES_BEFORE = (
    "'task', 'routine', 'pantry_item', 'shopping_item', 'pet', 'pet_event', 'transaction'"
)
FILE_ENTITY_TYPES_AFTER = f"{FILE_ENTITY_TYPES_BEFORE}, 'event'"


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("recurrence", sa.String(length=10), server_default="none", nullable=False),
        sa.Column("repeat_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "recurrence IN ('none', 'weekly', 'monthly', 'yearly')", name=op.f("ck_events_recurrence")
        ),
        sa.CheckConstraint(
            "end_time IS NULL OR (start_time IS NOT NULL AND end_time > start_time)",
            name=op.f("ck_events_end_time_after_start_time"),
        ),
        sa.CheckConstraint(
            "repeat_until IS NULL OR (recurrence <> 'none' AND repeat_until >= starts_on)",
            name=op.f("ck_events_repeat_until_matches_recurrence"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_events_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index("ix_events_user_id_starts_on", "events", ["user_id", "starts_on"], unique=False)
    # set_updated_at() comes from the initial migration.
    op.execute(
        "CREATE TRIGGER trg_events_set_updated_at BEFORE UPDATE ON events "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # Autogenerate ignores CHECK changes: files may now be attached to events.
    op.drop_constraint(op.f("ck_files_entity_type"), "files", type_="check")
    op.create_check_constraint(
        op.f("ck_files_entity_type"), "files", f"entity_type IN ({FILE_ENTITY_TYPES_AFTER})"
    )


def downgrade() -> None:
    # Refuse instead of deleting: event attachments are user data and their objects live in S3, which a
    # migration cannot clean up. Remove them through the API first. DDL is transactional, so nothing
    # below runs when this raises.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM files WHERE entity_type = 'event') THEN
                RAISE EXCEPTION 'Cannot downgrade: files still has rows with entity_type = ''event''.';
            END IF;
        END;
        $$
        """
    )
    op.drop_constraint(op.f("ck_files_entity_type"), "files", type_="check")
    op.create_check_constraint(
        op.f("ck_files_entity_type"), "files", f"entity_type IN ({FILE_ENTITY_TYPES_BEFORE})"
    )

    op.execute("DROP TRIGGER trg_events_set_updated_at ON events")
    op.drop_index("ix_events_user_id_starts_on", table_name="events")
    op.drop_table("events")
