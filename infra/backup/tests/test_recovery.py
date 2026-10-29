from backuptool.core import evaluate_health, plan_leftover_recovery

DB = "organizador"


def test_leftover_recovery_for_each_point_where_a_restore_can_die():
    # Nothing left behind.
    assert plan_leftover_recovery({DB, "postgres"}, DB) == []
    # pg_restore died: only the staging database is left.
    assert plan_leftover_recovery({DB, f"{DB}_restore"}, DB) == [("drop", f"{DB}_restore")]
    # Died between the renames: <db> is missing, the previous one is <db>_old -> it comes back first.
    assert plan_leftover_recovery({f"{DB}_old", f"{DB}_restore"}, DB) == [
        ("rename", f"{DB}_old", DB),
        ("drop", f"{DB}_restore"),
    ]
    # Died after the swap, before dropping the previous database.
    assert plan_leftover_recovery({DB, f"{DB}_old"}, DB) == [("drop", f"{DB}_old")]
    # No database at all (new server): nothing to recover, the restore creates it.
    assert plan_leftover_recovery({"postgres"}, DB) == []


def test_health_by_age_of_the_last_backup_and_of_the_container():
    hour = 3600.0
    now = 1_000 * hour
    old_container = now - 100 * hour

    assert evaluate_health(now - 25 * hour, old_container, now)[0] is True
    assert evaluate_health(now - 27 * hour, old_container, now)[0] is False
    assert evaluate_health(None, old_container, now)[0] is False
    # Just started (or the server was off): healthy until its first 03:00 run could have happened.
    assert evaluate_health(None, now - 2 * hour, now)[0] is True
    assert evaluate_health(now - 200 * hour, now - 2 * hour, now)[0] is True
