"""Backup, verification and restore of the Organizador (PostgreSQL + the files bucket of Garage).

Layout of `/backups` (the `backups/` folder of the repository, mounted in the container):

    2026-10-28_030000/            one complete backup (local time of APP_TIMEZONE)
        db.dump                   pg_dump -Fc (custom format, compressed)
        files/<key>               every object of the bucket, same key (<user_id>/<entity_type>/<uuid>)
        manifest.json             what is inside, with the SHA-256 of the dump and of each object
    pre-restore-2026-10-28_101500/  state saved by restore.sh before overwriting (outside the GFS rule)
    .tmp-<name>/                  backup in progress (or interrupted: removed by the next run)
    last_success.json             the last scheduled/manual backup that finished (format in README)
    .lock                         flock: one backup or restore at a time

Order: the database is dumped first, the bucket copied second. The API stores an object *before* its
`files` row and deletes the row *before* the object, so every row in the dump already had its object in
the bucket when the dump started. An object uploaded during the backup is at worst an extra object
(an orphan, removed by scripts.cleanup_orphans); only a file deleted by a user in the few seconds between
the dump and the copy leaves a row without object, and the manifest lists those (`rows_without_object`).
The reverse order would turn every upload during the (longer) copy into a row without object.
"""

import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backuptool.retention import backups_to_keep

logger = logging.getLogger("backup")

FORMAT_VERSION = 1
NAME_FORMAT = "%Y-%m-%d_%H%M%S"
DAILY_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
PRE_RESTORE_PREFIX = "pre-restore-"
PRE_RESTORE_NAME = re.compile(r"^pre-restore-\d{4}-\d{2}-\d{2}_\d{6}$")
TMP_PREFIX = ".tmp-"
DUMP_NAME = "db.dump"
MANIFEST_NAME = "manifest.json"
FILES_DIR = "files"
LAST_SUCCESS = "last_success.json"
LOCK_NAME = ".lock"
MAINTENANCE_DB = "postgres"
CHUNK_SIZE = 1024 * 1024
KINDS = ("scheduled", "manual", "pre-restore")


class BackupError(Exception):
    """A clear, expected failure: logged as one line, exit code 1."""


# --------------------------------------------------------------------------------------------------------
# Small helpers


def root() -> Path:
    return Path(os.environ.get("BACKUP_DIR", "/backups"))


def timezone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("TZ") or "UTC")


def now() -> datetime:
    return datetime.now(timezone())


def database_name() -> str:
    return os.environ["PGDATABASE"]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_path(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_atomic(path: Path, data: dict, *, mode: int = 0o600) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), mode)
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    fsync_path(path.parent)


def safe_relative_key(key: str) -> Path:
    """The object key as a relative path. Keys that could escape `files/` are refused."""
    parts = key.split("/")
    if not key or "\x00" in key or any(part in ("", ".", "..") for part in parts):
        raise BackupError(f"unsafe object key in the bucket: {key!r}")
    return Path(*parts)


def resolve_backup_dir(arg: str) -> Path:
    """Accept `<name>`, `backups/<name>` or `/backups/<name>` only: a backup directly inside the backup root,
    never a symbolic link."""
    given = Path(arg.rstrip("/") or arg)
    if len(given.parts) > 1 and given.parent not in (Path("backups"), root()):
        raise BackupError(
            f"refused: {arg!r} is not directly inside backups/ (copy the backup there first: backups/<name>)"
        )
    name = given.name
    if not (DAILY_NAME.match(name) or PRE_RESTORE_NAME.match(name)):
        raise BackupError(
            f"refused: {name!r} is not a backup name (AAAA-MM-DD_HHMMSS or pre-restore-AAAA-MM-DD_HHMMSS)"
        )
    path = root() / name
    if path.is_symlink():
        raise BackupError(f"refused: backups/{name} is a symbolic link (copy the real directory instead)")
    if not path.is_dir():
        raise BackupError(f"backup not found: backups/{name}")
    return path


@contextmanager
def exclusive_lock() -> Iterator[None]:
    """One backup or restore at a time (also across containers: flock on the bind-mounted folder)."""
    path = root() / LOCK_NAME
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError("another backup or restore is running (backups/.lock is held)") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-5:]
        raise BackupError(f"{cmd[0]} failed (exit {result.returncode}): " + " | ".join(detail))
    return result


def psql(sql: str, *, database: str | None = None) -> str:
    cmd = ["psql", "-X", "-w", "-At", "-v", "ON_ERROR_STOP=1", "-d", database or database_name(), "-c", sql]
    return run(cmd).stdout.strip()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# --------------------------------------------------------------------------------------------------------
# Reading the dump back: row counts, Alembic revision and the object keys referenced by `files`


_COPY_LINE = re.compile(r"^COPY (?P<table>\S+) \((?P<columns>[^)]*)\) FROM stdin;$")
_COPY_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}


def _copy_value(raw: str) -> str | None:
    if raw == r"\N":
        return None
    if "\\" not in raw:
        return raw
    return re.sub(r"\\(.)", lambda m: _COPY_ESCAPES.get(m.group(1), m.group(1)), raw)


@dataclass
class DumpContents:
    tables: dict[str, int] = field(default_factory=dict)
    alembic_revision: str | None = None
    file_keys: set[str] = field(default_factory=set)  # object keys of `files` rows in this bucket


def read_dump(dump: Path, bucket: str) -> DumpContents:
    """One streaming pass over the data of the dump (`pg_restore --data-only` to stdout). Also proves that
    pg_restore can read the whole file."""
    contents = DumpContents()
    cmd = ["pg_restore", "--data-only", "--file=-", str(dump)]
    # stderr goes to a file, not a pipe: a pipe nobody reads could fill up and block pg_restore while this
    # loop waits on stdout (deadlock).
    with (
        tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as errors,
        subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=errors, text=True, errors="surrogateescape"
        ) as proc,
    ):
        assert proc.stdout is not None
        table: str | None = None
        columns: list[str] = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            if table is None:
                match = _COPY_LINE.match(line)
                if match:
                    table = match["table"]
                    columns = [c.strip().strip('"') for c in match["columns"].split(",")]
                    contents.tables[table] = 0
                continue
            if line == r"\.":
                table = None
                continue
            contents.tables[table] += 1
            short = table.rsplit(".", 1)[-1]
            if short not in ("alembic_version", "files"):
                continue
            row = dict(zip(columns, (_copy_value(v) for v in line.split("\t")), strict=False))
            if short == "alembic_version":
                contents.alembic_revision = row.get("version_num")
            elif row.get("bucket") == bucket and row.get("object_key"):
                contents.file_keys.add(row["object_key"])
        proc.wait()
        errors.seek(0)
        stderr = errors.read()
    if proc.returncode != 0:
        raise BackupError(f"pg_restore could not read the dump: {stderr.strip()[-500:]}")
    return contents


# --------------------------------------------------------------------------------------------------------
# Backup


def clean_leftovers(base: Path) -> None:
    for leftover in base.glob(f"{TMP_PREFIX}*"):
        logger.warning("removing an interrupted backup: %s", leftover.name)
        shutil.rmtree(leftover, ignore_errors=True)


def directory_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def create_backup(kind: str) -> Path:
    """Write a complete backup and return its final directory. Nothing final exists if anything fails."""
    from backuptool.s3 import Bucket, ObjectGone

    if kind not in KINDS:
        raise BackupError(f"unknown kind: {kind}")
    base = root()
    if not base.is_dir() or not os.access(base, os.W_OK):
        raise BackupError(f"{base} does not exist or is not writable by uid {os.getuid()} (see BACKUP_UID)")

    started = now()
    clock = time.monotonic()
    name = started.strftime(NAME_FORMAT)
    if kind == "pre-restore":
        name = PRE_RESTORE_PREFIX + name
    final = base / name
    if final.exists():
        raise BackupError(f"{final.name} already exists (two backups in the same second?)")

    clean_leftovers(base)
    tmp = base / f"{TMP_PREFIX}{name}"
    tmp.mkdir()
    try:
        logger.info("backup %s started (%s)", name, kind)
        bucket = Bucket()

        # 1. Database.
        server_version = psql("SHOW server_version")
        pg_dump_version = run(["pg_dump", "--version"]).stdout.strip()
        dump = tmp / DUMP_NAME
        run(["pg_dump", "-w", "--format=custom", f"--file={dump}"])
        fsync_path(dump)
        dump_size, dump_sha = dump.stat().st_size, sha256_of(dump)
        contents = read_dump(dump, bucket.name)
        logger.info(
            "database %s dumped: %d bytes, %d tables, %d rows, alembic %s",
            database_name(),
            dump_size,
            len(contents.tables),
            sum(contents.tables.values()),
            contents.alembic_revision,
        )

        # 2. Files (after the dump: see the module docstring).
        objects = []
        files_dir = tmp / FILES_DIR
        files_dir.mkdir()
        for remote in bucket.list():
            relative = safe_relative_key(remote.key)
            dest = files_dir / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                got = bucket.download(remote.key, dest)
            except ObjectGone:
                logger.warning("object %s was deleted during the backup: skipped", remote.key)
                dest.unlink(missing_ok=True)
                continue
            objects.append(
                {
                    "key": remote.key,
                    "path": f"{FILES_DIR}/{relative.as_posix()}",
                    "size": got.size,
                    "sha256": got.sha256,
                    "content_type": got.content_type,
                }
            )
        copied = {obj["key"] for obj in objects}
        rows_without_object = sorted(contents.file_keys - copied)
        orphans = len(copied - contents.file_keys)
        total_bytes = sum(obj["size"] for obj in objects)
        logger.info("bucket %s copied: %d objects, %d bytes", bucket.name, len(objects), total_bytes)
        if orphans:
            logger.info("%d object(s) without a row in files (orphans; see scripts.cleanup_orphans)", orphans)
        for key in rows_without_object:
            logger.warning("row of files without object (deleted during the backup?): %s", key)

        # 3. Manifest, then the atomic rename.
        finished = now()
        manifest = {
            "format_version": FORMAT_VERSION,
            "name": name,
            "kind": kind,
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": finished.isoformat(timespec="seconds"),
            "timezone": str(timezone()),
            "order": "database dump first, then the bucket copy",
            "database": {
                "name": database_name(),
                "server_version": server_version,
                "pg_dump_version": pg_dump_version,
                "alembic_revision": contents.alembic_revision,
                "dump": {"path": DUMP_NAME, "size": dump_size, "sha256": dump_sha},
                "tables": dict(sorted(contents.tables.items())),
            },
            "files": {
                "bucket": bucket.name,
                "count": len(objects),
                "total_bytes": total_bytes,
                "objects_without_row": orphans,
                "rows_without_object": rows_without_object,
                "objects": sorted(objects, key=lambda obj: obj["key"]),
            },
        }
        write_json_atomic(tmp / MANIFEST_NAME, manifest)
        fsync_path(tmp)
        os.rename(tmp, final)
        fsync_path(base)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        logger.error("backup %s failed: no backup directory was created, last_success.json unchanged", name)
        raise

    size = directory_size(final)
    duration = round(time.monotonic() - clock, 1)
    logger.info("backup %s complete: %d bytes in %.1f s", name, size, duration)

    if kind != "pre-restore":
        write_json_atomic(
            base / LAST_SUCCESS,
            {
                "format_version": FORMAT_VERSION,
                "backup": name,
                "path": f"backups/{name}",
                "kind": kind,
                "started_at": manifest["started_at"],
                "finished_at": manifest["finished_at"],
                "duration_seconds": duration,
                "size_bytes": size,
                "database": {
                    "alembic_revision": contents.alembic_revision,
                    "dump_bytes": dump_size,
                },
                "files": {"count": len(objects), "bytes": total_bytes},
            },
            # No personal data: readable by the monitoring of the next delivery, whatever its uid.
            mode=0o644,
        )
    return final


def apply_retention(base: Path, today: date, protect: str) -> list[str]:
    """Delete the daily backups the GFS rule does not keep. Never touches pre-restore or `protect`."""
    by_time: dict[datetime, Path] = {}
    for path in base.iterdir():
        if path.is_dir() and DAILY_NAME.match(path.name):
            by_time[datetime.strptime(path.name, NAME_FORMAT)] = path
    keep = backups_to_keep(by_time, today)
    deleted = []
    for moment, path in sorted(by_time.items()):
        if moment in keep or path.name == protect:
            continue
        logger.info("retention: deleting %s", path.name)
        shutil.rmtree(path)
        deleted.append(path.name)
    logger.info("retention: %d kept, %d deleted", len(by_time) - len(deleted), len(deleted))
    return deleted


def backup(kind: str) -> Path:
    with exclusive_lock():
        final = create_backup(kind)
        if kind != "pre-restore":
            # Read the new backup back before deleting old ones: a corrupt new backup never causes the
            # retention to delete good ones.
            verify(final)
            apply_retention(root(), now().date(), protect=final.name)
    return final


# --------------------------------------------------------------------------------------------------------
# Verification and description


def load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads((path / MANIFEST_NAME).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BackupError(f"{path.name}: manifest.json not found (incomplete backup?)") from None
    except json.JSONDecodeError as exc:
        raise BackupError(f"{path.name}: manifest.json is not valid JSON ({exc.msg})") from None
    if manifest.get("format_version") != FORMAT_VERSION:
        raise BackupError(f"{path.name}: unsupported manifest format_version")
    return manifest


def verify(path: Path) -> dict:
    """Check the manifest against the files on disk (sizes and SHA-256). Raises BackupError on any problem."""
    manifest = load_manifest(path)
    problems: list[str] = []
    try:
        dump_info = manifest["database"]["dump"]
        objects = manifest["files"]["objects"]
    except (KeyError, TypeError):
        raise BackupError(f"{path.name}: manifest.json is missing required fields") from None

    problems.extend(
        f"symbolic link inside the backup: {p.relative_to(path)}" for p in path.rglob("*") if p.is_symlink()
    )
    dump = path / DUMP_NAME
    if not dump.is_file():
        problems.append("db.dump is missing")
    elif dump.stat().st_size != dump_info["size"] or sha256_of(dump) != dump_info["sha256"]:
        problems.append("db.dump: size or SHA-256 differs from the manifest")

    listed = set()
    for obj in objects:
        relative = safe_relative_key(obj["key"])
        file = path / FILES_DIR / relative
        listed.add(file)
        if not file.is_file():
            problems.append(f"missing object file: {obj['key']}")
        elif file.stat().st_size != obj["size"] or sha256_of(file) != obj["sha256"]:
            problems.append(f"object differs from the manifest: {obj['key']}")
    extra = [p for p in (path / FILES_DIR).rglob("*") if p.is_file() and p not in listed]
    problems.extend(f"file not in the manifest: {p.relative_to(path)}" for p in extra)
    if manifest["files"].get("count") != len(objects):
        problems.append("files.count differs from the list of objects")

    if problems:
        for problem in problems:
            logger.error("%s: %s", path.name, problem)
        raise BackupError(f"{path.name}: {len(problems)} problem(s) found, backup NOT valid")
    logger.info("%s verified: db.dump and %d object(s) match the manifest (SHA-256)", path.name, len(objects))
    return manifest


def current_tables(only: Iterable[str] | None = None) -> dict[str, int]:
    """Row count of each table of the `public` schema (only those in `only`, when given)."""
    names = psql(
        "SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) FROM pg_tables "
        "WHERE schemaname = 'public' ORDER BY 1"
    ).splitlines()
    if only is not None:
        wanted = set(only)
        names = [name for name in names if name in wanted]
    if not names:
        return {}
    union = " UNION ALL ".join(f"SELECT '{n}', count(*) FROM {n}" for n in names)
    rows = psql(union).splitlines()
    return {table: int(count) for table, count in (row.split("|") for row in rows)}


def describe(path: Path) -> None:
    """What the restore of `path` would replace: the backup next to the current state."""
    from backuptool.s3 import Bucket

    manifest = verify(path)
    database = manifest["database"]
    files = manifest["files"]
    print(f"Backup {manifest['name']} ({manifest['kind']}), feito em {manifest['finished_at']}")
    print(f"  banco {database['name']}: revisão Alembic {database['alembic_revision']}, ", end="")
    print(f"{sum(database['tables'].values())} linhas em {len(database['tables'])} tabelas")
    print(f"  bucket {files['bucket']}: {files['count']} objeto(s), {files['total_bytes']} bytes")

    print("Estado atual (será substituído):")
    try:
        revision = psql("SELECT version_num FROM alembic_version") or "-"
    except BackupError:
        revision = "? (sem tabela alembic_version)"
    try:
        tables = current_tables()
        print(f"  banco {database_name()}: revisão Alembic {revision}, ", end="")
        print(f"{sum(tables.values())} linhas em {len(tables)} tabelas")
    except BackupError as exc:
        tables = {}
        print(f"  banco {database_name()}: não foi possível ler ({exc})")
    bucket = Bucket()
    remote = list(bucket.list())
    print(f"  bucket {bucket.name}: {len(remote)} objeto(s), {sum(o.size for o in remote)} bytes")

    print("Tabelas (atual -> backup):")
    for table in sorted(set(tables) | set(database["tables"])):
        before = tables.get(table, "-")
        after = database["tables"].get(table, "-")
        mark = "" if before == after else "  *"
        print(f"  {table}: {before} -> {after}{mark}")


# --------------------------------------------------------------------------------------------------------
# Restore


# The database is never dropped before its replacement is ready. Names used during a restore:
#   <db>_restore  staging database, filled by pg_restore (dropped if pg_restore fails)
#   <db>_old      the previous database, between the two renames of the swap
# Swap: <db> -> <db>_old, then <db>_restore -> <db> (undone if it fails), then DROP <db>_old.
# Whatever moment the process dies at, one of <db> or <db>_old holds a complete database, and the next
# restore (or `backuptool recover`) puts things back with plan_leftover_recovery before anything else.

UNTOUCHED = "untouched"  # database and bucket as before (at most extra, harmless objects in the bucket)
DATABASE_RESTORED = "database-restored"  # the database is the backup's; the bucket may still have extras
UNKNOWN = "unknown"  # died or failed in the middle of the swap: see `backuptool recover`


class RestoreFailed(BackupError):
    def __init__(self, state: str, message: str) -> None:
        super().__init__(message)
        self.state = state


def staging_name(target: str) -> str:
    return f"{target}_restore"


def old_name(target: str) -> str:
    return f"{target}_old"


def plan_leftover_recovery(existing: set[str], target: str) -> list[tuple[str, ...]]:
    """Actions that undo what an interrupted restore left behind, given the existing database names.

    - `<db>` missing and `<db>_old` present: died between the two renames -> rename `_old` back.
    - `<db>` and `<db>_old` present: died after the swap, before the drop -> drop `_old`.
    - `<db>_restore` present: an unfinished staging database -> drop it (it only goes live by the rename).
    """
    old, staging = old_name(target), staging_name(target)
    actions: list[tuple[str, ...]] = []
    if target not in existing and old in existing:
        actions.append(("rename", old, target))
    elif old in existing:
        actions.append(("drop", old))
    if staging in existing:
        actions.append(("drop", staging))
    return actions


def existing_databases() -> set[str]:
    return set(psql("SELECT datname FROM pg_database", database=MAINTENANCE_DB).splitlines())


def drop_database(name: str) -> None:
    psql(f"DROP DATABASE IF EXISTS {quote_ident(name)} WITH (FORCE)", database=MAINTENANCE_DB)


def rename_database(name: str, new_name: str, attempts: int = 5) -> None:
    """ALTER DATABASE ... RENAME needs no session on it: end them first (Adminer, a psql left open) and
    retry a few times in case one reconnects in between."""
    for attempt in range(1, attempts + 1):
        psql(
            "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity "
            f"WHERE datname = '{name}' AND pid <> pg_backend_pid()",
            database=MAINTENANCE_DB,
        )
        try:
            psql(
                f"ALTER DATABASE {quote_ident(name)} RENAME TO {quote_ident(new_name)}",
                database=MAINTENANCE_DB,
            )
            return
        except BackupError:
            if attempt == attempts:
                raise
            time.sleep(1)


def recover_leftover_databases() -> None:
    target = database_name()
    for action in plan_leftover_recovery(existing_databases(), target):
        if action[0] == "rename":
            logger.warning("recovery: %s is missing, renaming %s back to %s", target, action[1], action[2])
            rename_database(action[1], action[2])
        else:
            logger.warning("recovery: dropping %s, left by an interrupted restore", action[1])
            drop_database(action[1])
    if target not in existing_databases():
        logger.warning("database %s does not exist: the restore will create it", target)


def test_hook(point: str) -> None:
    """Failure injection for the failure tests only: BACKUP_TEST_HOOK=exit:<point> kills the process
    (like a `kill -9`), pause:<point> waits 30 s (time to stop Garage by hand). Points: between-renames,
    before-upload, after-first-upload."""
    hook = os.environ.get("BACKUP_TEST_HOOK", "")
    action, _, where = hook.partition(":")
    if where != point:
        return
    if action == "exit":
        logger.warning("BACKUP_TEST_HOOK: dying at %s", point)
        os._exit(137)
    if action == "pause":
        logger.warning("BACKUP_TEST_HOOK: pausing 30 s at %s", point)
        time.sleep(30)


def stage_database(dump: Path) -> None:
    """pg_restore into `<db>_restore`. The live database is not touched; a failure drops the staging."""
    staging = staging_name(database_name())
    logger.info("database: restoring into the staging database %s", staging)
    drop_database(staging)
    psql(f"CREATE DATABASE {quote_ident(staging)} TEMPLATE template0", database=MAINTENANCE_DB)
    try:
        run(
            [
                "pg_restore",
                "-w",
                "--no-owner",
                "--exit-on-error",
                "--single-transaction",
                f"--dbname={staging}",
                str(dump),
            ]
        )
    except BackupError:
        try:
            drop_database(staging)
        except BackupError:
            logger.warning("could not drop %s (the next restore drops it)", staging)
        raise
    logger.info("database: pg_restore into %s done", staging)


class SwapUndone(BackupError):
    """The swap failed and was undone: the previous database is live again."""


def swap_database() -> None:
    target = database_name()
    staging, old = staging_name(target), old_name(target)
    had_target = target in existing_databases()
    if had_target:
        rename_database(target, old)
        test_hook("between-renames")
    try:
        rename_database(staging, target)
    except BackupError as exc:
        if not had_target:
            raise
        try:
            rename_database(old, target)
        except BackupError:
            logger.critical("could NOT rename %s back to %s: run `backuptool recover`", old, target)
            raise exc from None
        raise SwapUndone(f"swap failed and was undone, {target} is the previous database: {exc}") from exc
    logger.info("database: %s is now the restored database", target)
    if had_target:
        try:
            drop_database(old)
        except BackupError as exc:
            logger.warning(
                "could not drop %s (the next restore or `backuptool recover` drops it): %s", old, exc
            )


def upload_missing_objects(path: Path, manifest: dict) -> dict[str, int]:
    """Additive step: send the objects of the backup that are missing or different. Deletes nothing."""
    from backuptool.s3 import Bucket, md5_of

    test_hook("before-upload")
    bucket = Bucket()
    current = {obj.key: obj for obj in bucket.list()}
    uploaded = unchanged = 0
    for obj in sorted(manifest["files"]["objects"], key=lambda o: o["key"]):
        key = obj["key"]
        file = path / FILES_DIR / safe_relative_key(key)
        remote = current.get(key)
        # ETag = MD5 for single-part uploads; multipart ETags never match, so those are sent again.
        if remote and remote.size == obj["size"] and remote.etag == md5_of(file):
            unchanged += 1
            continue
        bucket.upload(file, key, obj["content_type"])
        uploaded += 1
        test_hook("after-first-upload")
    logger.info("bucket: %d uploaded, %d unchanged (nothing deleted yet)", uploaded, unchanged)
    return {"uploaded": uploaded, "unchanged": unchanged}


def delete_extra_objects(manifest: dict) -> None:
    """Last step: delete the objects that are not in the backup. A failure here only leaves orphans."""
    from backuptool.s3 import Bucket

    bucket = Bucket()
    wanted = {obj["key"]: obj["size"] for obj in manifest["files"]["objects"]}
    deleted = failed = 0
    for remote in list(bucket.list()):
        if remote.key in wanted:
            continue
        try:
            bucket.delete(remote.key)
            deleted += 1
        except Exception:
            logger.warning("could not delete the extra object %s", remote.key, exc_info=True)
            failed += 1
    logger.info("bucket: %d extra object(s) deleted", deleted)
    if failed:
        logger.warning(
            "bucket: %d extra object(s) left behind: harmless orphans, removed by "
            "`docker compose exec api python -m scripts.cleanup_orphans` (after 24 h)",
            failed,
        )
    after = {obj.key: obj.size for obj in bucket.list()}
    missing = [key for key, size in wanted.items() if after.get(key) != size]
    if missing:
        raise BackupError(
            f"{len(missing)} object(s) of the backup are missing in the bucket after the restore"
        )
    logger.info("bucket: %s has every object of the backup (%d)", bucket.name, len(wanted))


def check_row_counts(manifest: dict) -> None:
    expected = manifest["database"]["tables"]
    actual = current_tables(only=expected)
    differences = [
        f"{table}: {actual.get(table, 'missing')} (backup: {count})"
        for table, count in sorted(expected.items())
        if actual.get(table) != count
    ]
    if differences:
        raise BackupError(
            "the database WAS restored, but the row counts differ from the manifest in: "
            + "; ".join(differences)
        )
    logger.info("database: row counts of the %d tables match the manifest", len(expected))


def restore(path: Path, *, safety_backup: bool) -> Path | None:
    """Restore `path` under a single lock (no backup can run in the middle). Returns the pre-restore
    directory. Order: recover leftovers -> verify -> safety backup -> staging database -> upload missing
    objects -> swap the database -> delete extra objects -> check counts."""
    from backuptool.s3 import Bucket

    state = UNTOUCHED
    pre_restore = None
    with exclusive_lock():
        try:
            recover_leftover_databases()
            manifest = verify(path)
            bucket_name = Bucket().name
            if manifest["files"]["bucket"] != bucket_name:
                raise BackupError(
                    f"the backup is of bucket {manifest['files']['bucket']!r}, S3_BUCKET is {bucket_name!r}"
                )
            if manifest["database"]["name"] != database_name():
                logger.warning(
                    "the backup is of database %s; restoring into %s",
                    manifest["database"]["name"],
                    database_name(),
                )
            if safety_backup:
                pre_restore = create_backup("pre-restore")
                print(f"PRE_RESTORE_DIR={pre_restore.name}", flush=True)

            stage_database(path / DUMP_NAME)
            upload_missing_objects(path, manifest)
            state = UNKNOWN
            try:
                swap_database()
            except SwapUndone:
                state = UNTOUCHED
                raise
            state = DATABASE_RESTORED
            delete_extra_objects(manifest)
            check_row_counts(manifest)
        except Exception as exc:
            if state == UNTOUCHED:
                try:
                    drop_database(staging_name(database_name()))
                except Exception:
                    logger.warning("could not drop the staging database (the next restore drops it)")
            raise RestoreFailed(state, str(exc)) from exc
    logger.info("restore of %s complete", path.name)
    return pre_restore


def recover() -> None:
    """Only the leftover recovery (what restore.sh suggests after a crash)."""
    with exclusive_lock():
        recover_leftover_databases()
        logger.info("recovery done: databases %s", ", ".join(sorted(existing_databases())))


# --------------------------------------------------------------------------------------------------------
# Health (healthcheck of the `backup` service)

MAX_AGE_HOURS = 26


def evaluate_health(
    last_finished: float | None, container_started: float, now_ts: float, max_age_hours: float = MAX_AGE_HOURS
) -> tuple[bool, str]:
    """Healthy when the last successful backup is at most `max_age_hours` old. Without one that recent, a
    container started less than `max_age_hours` ago is still healthy: its 03:00 run has not come yet."""
    limit = max_age_hours * 3600
    if last_finished is not None and now_ts - last_finished <= limit:
        return True, f"last successful backup {(now_ts - last_finished) / 3600:.1f} h ago"
    if now_ts - container_started <= limit:
        return True, f"no backup in the last {max_age_hours} h yet; container up for " + (
            f"{(now_ts - container_started) / 3600:.1f} h, waiting for the 03:00 run"
        )
    if last_finished is None:
        return False, f"no successful backup and the container is up for more than {max_age_hours} h"
    return (
        False,
        f"last successful backup {(now_ts - last_finished) / 3600:.1f} h ago (limit {max_age_hours} h)",
    )


def container_started_at() -> float:
    """Start time of PID 1 (the container's main process), from /proc."""
    start_ticks = int(Path("/proc/1/stat").read_text().rsplit(")", 1)[1].split()[19])
    boot = next(
        int(line.split()[1])
        for line in Path("/proc/stat").read_text().splitlines()
        if line.startswith("btime ")
    )
    return boot + start_ticks / os.sysconf("SC_CLK_TCK")


def health() -> tuple[bool, str]:
    path = root() / LAST_SUCCESS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        last = datetime.fromisoformat(data["finished_at"]).timestamp()
    except FileNotFoundError:
        last = None
    except (ValueError, KeyError, TypeError):
        return False, "last_success.json is not valid"
    return evaluate_health(last, container_started_at(), time.time())
