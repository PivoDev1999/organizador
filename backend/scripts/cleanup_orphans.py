"""Remove orphan objects from the files bucket: objects that no row of `files` points to.

Usage (from backend/): python -m scripts.cleanup_orphans [--dry-run]

Orphans appear when deleting an object fails after its row was already deleted (the API logs it and
moves on), when a failed upload could not remove its object, or when the seed recreates the demo user.
Objects younger than MIN_AGE (24 hours) are kept: they may belong to an upload still in progress (the
object is stored before its row). The margin is wide on purpose: the LastModified of an object sent in
multipart counts from the *start* of the upload, not from its end, so an object that has only just
become visible (and whose row is about to be inserted) can already look old after a slow upload.

Rows whose object is missing are only reported, never deleted: that needs a person to look at it
(restore from backup or delete the attachment through the API).
"""

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.core.storage import Storage, StorageError
from app.repositories import file as file_repo

MIN_AGE = timedelta(hours=24)

logger = logging.getLogger(__name__)


@dataclass
class CleanupReport:
    deleted: list[str] = field(default_factory=list)  # in a dry run: would be deleted
    kept_recent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    rows_without_object: list[uuid.UUID] = field(default_factory=list)


def cleanup_orphans(
    db: Session, storage: Storage, *, now: datetime | None = None, dry_run: bool = False
) -> CleanupReport:
    now = now or clock.now_utc()
    report = CleanupReport()
    # Rows first, objects second: an upload finishing in between has an object newer than MIN_AGE
    # (kept), never a row that makes a listed object look like an orphan for good.
    ids_by_key = file_repo.ids_by_object_key(db, storage.bucket)
    db.rollback()
    listed: set[str] = set()
    for obj in storage.list():
        listed.add(obj.key)
        if obj.key in ids_by_key:
            continue
        if now - obj.last_modified < MIN_AGE:
            report.kept_recent.append(obj.key)
            continue
        if not dry_run:
            try:
                storage.delete(obj.key)
            except StorageError:
                logger.exception("Could not delete orphan object %s", obj.key)
                report.failed.append(obj.key)
                continue
        report.deleted.append(obj.key)
    report.rows_without_object = sorted(file_id for key, file_id in ids_by_key.items() if key not in listed)
    return report


def main(argv: list[str] | None = None) -> None:
    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.core.storage import S3Storage

    parser = argparse.ArgumentParser(description="Remove objetos do bucket sem linha em `files`.")
    parser.add_argument("--dry-run", action="store_true", help="só lista o que seria apagado")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    storage = S3Storage.from_settings(get_settings())
    try:
        with SessionLocal() as db:
            report = cleanup_orphans(db, storage, dry_run=args.dry_run)
    except StorageError as exc:
        sys.exit(f"Erro: não foi possível acessar o armazenamento ({exc}).")

    verb = "Seriam apagados" if args.dry_run else "Apagados"
    print(f"{verb} {len(report.deleted)} objeto(s) órfão(s) do bucket '{storage.bucket}'.")
    for key in report.deleted:
        print(f"  - {key}")
    if report.kept_recent:
        recent = len(report.kept_recent)
        hours = int(MIN_AGE.total_seconds() // 3600)
        print(f"Mantidos {recent} objeto(s) órfão(s) com menos de {hours} horas (upload em curso).")
    if report.rows_without_object:
        print(f"Atenção: {len(report.rows_without_object)} arquivo(s) sem objeto no armazenamento (ids):")
        for file_id in report.rows_without_object:
            print(f"  - {file_id}")
    if report.failed:
        sys.exit(f"Erro: {len(report.failed)} objeto(s) não puderam ser apagados (veja o log).")


if __name__ == "__main__":
    main()
