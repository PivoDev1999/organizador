"""initial schema

Revision ID: b0e9e518b85c
Revises:
Create Date: 2026-10-19 19:21:44.149529

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b0e9e518b85c"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen on purpose: a migration must not import the current models.
TABLES = (
    "users",
    "tasks",
    "routines",
    "routine_logs",
    "pantry_items",
    "shopping_items",
    "pets",
    "pet_events",
    "transactions",
    "budgets",
    "files",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index("uq_users_email_lower", "users", [sa.literal_column("lower(email)")], unique=True)
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("EXTRACT(DAY FROM month) = 1", name=op.f("ck_budgets_month_first_day")),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_budgets_amount_non_negative")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_budgets_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
        sa.UniqueConstraint("user_id", "category", "month", name=op.f("uq_budgets_user_id_category_month")),
    )
    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("bucket", sa.String(length=63), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('task', 'routine', 'pantry_item', 'shopping_item', 'pet', 'pet_event', "
            "'transaction')",
            name=op.f("ck_files_entity_type"),
        ),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_files_size_bytes_non_negative")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_files_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        sa.UniqueConstraint("bucket", "object_key", name=op.f("uq_files_bucket_object_key")),
    )
    op.create_index("ix_files_entity_type_entity_id", "files", ["entity_type", "entity_id"], unique=False)
    op.create_index(op.f("ix_files_user_id"), "files", ["user_id"], unique=False)
    op.create_table(
        "pantry_items",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=3), server_default="0", nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("min_quantity", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("min_quantity >= 0", name=op.f("ck_pantry_items_min_quantity_non_negative")),
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_pantry_items_quantity_non_negative")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_pantry_items_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pantry_items")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_pantry_items_id_user_id")),
    )
    op.create_index(
        "ix_pantry_items_user_id_expires_on", "pantry_items", ["user_id", "expires_on"], unique=False
    )
    op.create_table(
        "pets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("species", sa.String(length=50), nullable=False),
        sa.Column("breed", sa.String(length=100), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("weight_kg > 0", name=op.f("ck_pets_weight_kg_positive")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_pets_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pets")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_pets_id_user_id")),
    )
    op.create_index(op.f("ix_pets_user_id"), "pets", ["user_id"], unique=False)
    op.create_table(
        "routines",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(length=10), nullable=False),
        sa.Column("days_of_week", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("day_of_month", sa.SmallInteger(), nullable=True),
        sa.Column("time_of_day", sa.Time(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            # cardinality(NULL) is NULL and a NULL CHECK result passes, hence the explicit IS NOT NULL.
            "(frequency = 'daily' AND days_of_week IS NULL AND day_of_month IS NULL) OR "
            "(frequency = 'weekly' AND days_of_week IS NOT NULL AND cardinality(days_of_week) > 0 "
            "AND day_of_month IS NULL) OR "
            "(frequency = 'monthly' AND day_of_month IS NOT NULL AND days_of_week IS NULL)",
            name=op.f("ck_routines_schedule_matches_frequency"),
        ),
        sa.CheckConstraint("frequency IN ('daily', 'weekly', 'monthly')", name=op.f("ck_routines_frequency")),
        sa.CheckConstraint(
            "array_ndims(days_of_week) = 1", name=op.f("ck_routines_days_of_week_one_dimension")
        ),
        sa.CheckConstraint("day_of_month BETWEEN 1 AND 31", name=op.f("ck_routines_day_of_month_range")),
        sa.CheckConstraint(
            "days_of_week <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[]",
            name=op.f("ck_routines_days_of_week_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_routines_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routines")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_routines_id_user_id")),
    )
    op.create_index(op.f("ix_routines_user_id"), "routines", ["user_id"], unique=False)
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="todo", nullable=False),
        sa.Column("priority", sa.String(length=10), server_default="medium", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(status = 'done') = (completed_at IS NOT NULL)",
            name=op.f("ck_tasks_completed_at_matches_status"),
        ),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name=op.f("ck_tasks_priority")),
        sa.CheckConstraint("status IN ('todo', 'doing', 'done')", name=op.f("ck_tasks_status")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_tasks_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("ix_tasks_user_id_due_date", "tasks", ["user_id", "due_date"], unique=False)
    op.create_index("ix_tasks_user_id_status", "tasks", ["user_id", "status"], unique=False)
    op.create_table(
        "pet_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pet_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("next_due_on", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "type IN ('vaccine', 'vet', 'medication', 'grooming', 'other')", name=op.f("ck_pet_events_type")
        ),
        sa.CheckConstraint(
            "next_due_on IS NULL OR next_due_on >= occurred_on",
            name=op.f("ck_pet_events_next_due_after_occurred"),
        ),
        sa.ForeignKeyConstraint(
            ["pet_id", "user_id"],
            ["pets.id", "pets.user_id"],
            name=op.f("fk_pet_events_pet_id_pets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_pet_events_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pet_events")),
    )
    op.create_index(op.f("ix_pet_events_pet_id"), "pet_events", ["pet_id"], unique=False)
    op.create_index(
        "ix_pet_events_user_id_next_due_on", "pet_events", ["user_id", "next_due_on"], unique=False
    )
    op.create_table(
        "routine_logs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("routine_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("done_on", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["routine_id", "user_id"],
            ["routines.id", "routines.user_id"],
            name=op.f("fk_routine_logs_routine_id_routines"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_routine_logs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routine_logs")),
        sa.UniqueConstraint("routine_id", "done_on", name=op.f("uq_routine_logs_routine_id_done_on")),
    )
    op.create_index("ix_routine_logs_user_id_done_on", "routine_logs", ["user_id", "done_on"], unique=False)
    op.create_table(
        "shopping_items",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("estimated_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("is_purchased", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pantry_item_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "estimated_price >= 0", name=op.f("ck_shopping_items_estimated_price_non_negative")
        ),
        sa.CheckConstraint(
            "is_purchased = (purchased_at IS NOT NULL)",
            name=op.f("ck_shopping_items_purchased_at_matches_is_purchased"),
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_shopping_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["pantry_item_id", "user_id"],
            ["pantry_items.id", "pantry_items.user_id"],
            name=op.f("fk_shopping_items_pantry_item_id_pantry_items"),
            ondelete="SET NULL (pantry_item_id)",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_shopping_items_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_items")),
    )
    op.create_index(
        op.f("ix_shopping_items_pantry_item_id"), "shopping_items", ["pantry_item_id"], unique=False
    )
    op.create_index(
        "ix_shopping_items_user_id_is_purchased", "shopping_items", ["user_id", "is_purchased"], unique=False
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pet_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("type IN ('income', 'expense')", name=op.f("ck_transactions_type")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_transactions_amount_positive")),
        sa.ForeignKeyConstraint(
            ["pet_id", "user_id"],
            ["pets.id", "pets.user_id"],
            name=op.f("fk_transactions_pet_id_pets"),
            ondelete="SET NULL (pet_id)",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_transactions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
    )
    op.create_index(op.f("ix_transactions_pet_id"), "transactions", ["pet_id"], unique=False)
    op.create_index("ix_transactions_user_id_category", "transactions", ["user_id", "category"], unique=False)
    op.create_index("ix_transactions_user_id_due_date", "transactions", ["user_id", "due_date"], unique=False)

    # updated_at is kept by the database so raw SQL and bulk updates are covered too.
    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
        """
    )
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TRIGGER trg_{table}_set_updated_at ON {table}")
    op.execute("DROP FUNCTION set_updated_at()")

    op.drop_index("ix_transactions_user_id_due_date", table_name="transactions")
    op.drop_index("ix_transactions_user_id_category", table_name="transactions")
    op.drop_index(op.f("ix_transactions_pet_id"), table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_shopping_items_user_id_is_purchased", table_name="shopping_items")
    op.drop_index(op.f("ix_shopping_items_pantry_item_id"), table_name="shopping_items")
    op.drop_table("shopping_items")
    op.drop_index("ix_routine_logs_user_id_done_on", table_name="routine_logs")
    op.drop_table("routine_logs")
    op.drop_index("ix_pet_events_user_id_next_due_on", table_name="pet_events")
    op.drop_index(op.f("ix_pet_events_pet_id"), table_name="pet_events")
    op.drop_table("pet_events")
    op.drop_index("ix_tasks_user_id_status", table_name="tasks")
    op.drop_index("ix_tasks_user_id_due_date", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index(op.f("ix_routines_user_id"), table_name="routines")
    op.drop_table("routines")
    op.drop_index(op.f("ix_pets_user_id"), table_name="pets")
    op.drop_table("pets")
    op.drop_index("ix_pantry_items_user_id_expires_on", table_name="pantry_items")
    op.drop_table("pantry_items")
    op.drop_index(op.f("ix_files_user_id"), table_name="files")
    op.drop_index("ix_files_entity_type_entity_id", table_name="files")
    op.drop_table("files")
    op.drop_table("budgets")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
