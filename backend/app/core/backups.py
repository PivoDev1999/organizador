"""Read-only access to backups/last_success.json, the summary the `backup` service writes after each
successful backup (format in the README, section "Formato do last_success.json").

The API never reads the backups themselves: their directories are 0700 of BACKUP_UID, unreadable for the
API's uid. Only this file is world-readable (0644), and in the Docker stack the folder is mounted read-only.
"""

import json
import os
import stat
from pathlib import Path

LAST_SUCCESS = "last_success.json"
# The real file has under 1 KB; anything much larger is not ours.
MAX_BYTES = 64 * 1024


class BackupInfoUnreadable(Exception):
    """last_success.json exists but cannot be read (permissions, I/O) or is not valid JSON."""


def read_last_success(backups_dir: Path) -> object | None:
    """The parsed JSON, or None when there is no last_success.json (no backup finished yet, or the folder
    is not there).

    Opened without following a symlink and without blocking (O_NOFOLLOW | O_NONBLOCK), and read only if it
    is a regular file: a symlink, a FIFO or a device in its place is "unreadable", never a hung request.
    """
    path = backups_dir / LAST_SUCCESS
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:  # permissions, ELOOP (a symlink), ...
        raise BackupInfoUnreadable("cannot open last_success.json") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BackupInfoUnreadable("last_success.json is not a regular file")
        content = b""
        while len(content) <= MAX_BYTES and (chunk := os.read(fd, MAX_BYTES + 1 - len(content))):
            content += chunk
    except OSError as exc:
        raise BackupInfoUnreadable("cannot read last_success.json") from exc
    finally:
        os.close(fd)
    if len(content) > MAX_BYTES:
        raise BackupInfoUnreadable("last_success.json is too large")
    try:
        return json.loads(content)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise BackupInfoUnreadable("last_success.json is not valid JSON") from exc
