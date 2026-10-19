from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Connection, inspect, text

from alembic import command
from app.core.database import engine
from app.models import Base

# Throwaway schema built straight from the models, used as the reference for the migrated "public".
MODELS_SCHEMA = "schema_from_models"


def _tables() -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_downgrade_to_base_and_upgrade_to_head(alembic_config: Config):
    try:
        command.downgrade(alembic_config, "base")
        assert _tables() == set()
    finally:
        # Other tests rely on the schema, so always leave the database at head.
        command.upgrade(alembic_config, "head")

    assert _tables() == set(Base.metadata.tables)


def test_alembic_check_finds_no_pending_operations(alembic_config: Config):
    # Autogenerate compares tables, columns, types, nullability, indexes, unique constraints and FKs
    # (including ON DELETE). It ignores CHECK constraints and triggers: see the tests below.
    command.check(alembic_config)


@pytest.fixture(scope="module")
def models_schema() -> Iterator[Connection]:
    """Connection where MODELS_SCHEMA holds a create_all() of the models; rolled back at the end."""
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text(f"CREATE SCHEMA {MODELS_SCHEMA}"))
        Base.metadata.create_all(connection.execution_options(schema_translate_map={None: MODELS_SCHEMA}))
        try:
            yield connection
        finally:
            transaction.rollback()


def _constraints(connection: Connection, schema: str) -> dict[tuple[str, str], str]:
    rows = connection.execute(
        text(
            """
            SELECT cl.relname, con.conname, pg_get_constraintdef(con.oid)
            FROM pg_constraint con
            JOIN pg_class cl ON cl.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = cl.relnamespace
            WHERE ns.nspname = :schema AND cl.relname <> 'alembic_version'
            """
        ),
        {"schema": schema},
    )
    # FK definitions qualify tables outside the search_path: strip the schema to compare.
    return {(table, name): definition.replace(f"{schema}.", "") for table, name, definition in rows}


def _indexes(connection: Connection, schema: str) -> dict[tuple[str, str], str]:
    rows = connection.execute(
        text(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename <> 'alembic_version'"
        ),
        {"schema": schema},
    )
    return {(table, name): definition.replace(f"{schema}.", "") for table, name, definition in rows}


def test_migrated_constraints_match_models(models_schema: Connection):
    """Covers CHECKs too: both sides are normalized by PostgreSQL itself, so plain text equality works."""
    migrated = _constraints(models_schema, "public")
    expected = _constraints(models_schema, MODELS_SCHEMA)

    migrated_checks = {key for key, definition in migrated.items() if definition.startswith("CHECK")}
    expected_checks = {key for key, definition in expected.items() if definition.startswith("CHECK")}
    assert migrated_checks == expected_checks
    assert migrated == expected


def test_migrated_indexes_match_models(models_schema: Connection):
    assert _indexes(models_schema, "public") == _indexes(models_schema, MODELS_SCHEMA)


def test_every_table_has_updated_at_trigger():
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT cl.relname
                FROM pg_trigger tg
                JOIN pg_class cl ON cl.oid = tg.tgrelid
                JOIN pg_namespace ns ON ns.oid = cl.relnamespace
                JOIN pg_proc fn ON fn.oid = tg.tgfoid
                WHERE ns.nspname = 'public'
                  AND NOT tg.tgisinternal
                  AND tg.tgname = 'trg_' || cl.relname || '_set_updated_at'
                  AND fn.proname = 'set_updated_at'
                  -- tgtype bits: 1 = FOR EACH ROW, 2 = BEFORE, 16 = UPDATE
                  AND tg.tgtype & (1 | 2 | 16) = (1 | 2 | 16)
                """
            )
        )
        assert {table for (table,) in rows} == set(Base.metadata.tables)
