"""One consistent, read-only view of the database for reads that span several tables (the dashboard)."""

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

SNAPSHOT_STATEMENT = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"


class SnapshotUnavailableError(RuntimeError):
    """The consistent snapshot could not be applied; serving the reads anyway could mix instants."""


def begin_read_snapshot(db: Session, *, require: bool = True) -> bool:
    """Start a REPEATABLE READ, READ ONLY transaction: every following query sees the same snapshot
    (the one taken by the first of them), whatever other requests commit meanwhile, and nothing can
    be written by mistake. Returns whether the level was applied.

    `SET TRANSACTION` must be the first statement of a transaction, so the current one is ended first:
    in a request it only holds the authentication lookup, a read with nothing to write (commit, not
    rollback, so the loaded user is not expired). The setting lasts until that transaction ends; the
    pooled connection goes back to its default level afterwards.

    A session joined to an outer transaction it does not own (the test fixture `db_session`, which runs
    everything inside savepoints) cannot change it: Postgres refuses `SET TRANSACTION` inside a
    savepoint. Strict by default (`require=True`): that case raises SnapshotUnavailableError (a logged
    500), so an inconsistent result is never served silently. Only the test suite passes
    `require=False` (setting `dashboard_require_snapshot`), and then this returns False and the level
    is left to the owner of the outer transaction. The guarantee itself is tested with real sessions
    (tests/test_dashboard_concurrency.py).
    """
    if db.in_transaction():
        db.commit()
    bind = db.get_bind()
    if isinstance(bind, Connection) and bind.in_transaction():
        if require:
            raise SnapshotUnavailableError(
                "Cannot start the REPEATABLE READ, READ ONLY snapshot: the session is joined to an outer "
                "transaction it does not own."
            )
        return False
    db.execute(text(SNAPSHOT_STATEMENT))
    return True
