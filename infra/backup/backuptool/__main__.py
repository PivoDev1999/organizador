"""Command line of the backup container: python -m backuptool <command>.

    run [--kind scheduled|manual|pre-restore]   new backup (+ retention, except pre-restore)
    verify <dir>                                checks manifest.json and every SHA-256
    describe <dir>                              the backup next to the current state (used by restore.sh)
    restore <dir> [--safety-backup]             pre-restore backup + database + bucket, under one lock
    recover                                     undo what an interrupted restore left (<db>_old, <db>_restore)
    health                                      healthcheck: last_success.json at most 26 h old
    list-objects                                keys and sizes of the bucket (used by the end-to-end test)

Machine-readable lines on stdout: BACKUP_DIR=<name> (run), PRE_RESTORE_DIR=<name> and, when a restore
fails, RESTORE_STATE=untouched|database-restored|unknown (read by restore.sh).
"""

import argparse
import logging
import os
import sys

from botocore.exceptions import BotoCoreError, ClientError

from backuptool import core


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backuptool", description="Backup e restauração do Organizador.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="faz um backup agora")
    run.add_argument("--kind", choices=core.KINDS, default="manual")
    for name in ("verify", "describe"):
        commands.add_parser(name).add_argument("directory")
    restore = commands.add_parser("restore")
    restore.add_argument("directory")
    restore.add_argument("--safety-backup", action="store_true", help="pre-restore backup first")
    for name in ("recover", "health", "list-objects"):
        commands.add_parser(name)
    args = parser.parse_args(argv)
    # Backups hold personal data and password hashes: only BACKUP_UID can read them.
    os.umask(0o077)

    if args.command == "health":
        healthy, message = core.health()
        print(("healthy: " if healthy else "UNHEALTHY: ") + message)
        return 0 if healthy else 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s backup: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )
    logger = logging.getLogger("backup")
    try:
        if args.command == "run":
            final = core.backup(args.kind)
            print(f"BACKUP_DIR={final.name}", flush=True)
        elif args.command == "verify":
            core.verify(core.resolve_backup_dir(args.directory))
        elif args.command == "describe":
            core.describe(core.resolve_backup_dir(args.directory))
        elif args.command == "restore":
            core.restore(core.resolve_backup_dir(args.directory), safety_backup=args.safety_backup)
        elif args.command == "recover":
            core.recover()
        elif args.command == "list-objects":
            from backuptool.s3 import Bucket

            for obj in Bucket().list():
                print(f"{obj.key}\t{obj.size}")
    except core.RestoreFailed as exc:
        logger.error("FAILED: %s", exc)
        print(f"RESTORE_STATE={exc.state}", flush=True)
        return 1
    except core.BackupError as exc:
        logger.error("FAILED: %s", exc)
        return 1
    except (BotoCoreError, ClientError) as exc:
        logger.error("FAILED: storage (S3) error: %s", exc)
        return 1
    except OSError:
        logger.exception("FAILED: file system or process error")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
