"""S3Storage against the real Garage, in the test bucket (S3_TEST_BUCKET, created by garage-init).

Every test works under its own random prefix and removes what it created. Skipped only when Garage is
not reachable at all (`docker compose up -d garage garage-init`); any other error fails.
"""

import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from botocore.exceptions import EndpointConnectionError

from app.core.config import get_settings
from app.core.storage import ObjectNotFound, S3Storage, StorageError

BIG = 9 * 1024 * 1024  # above the multipart threshold (8 MiB)


class NonSeekable(io.RawIOBase):
    """A stream that can only be read forward, like the size-limited reader of the files service."""

    def __init__(self, data: bytes, fail_after: int | None = None) -> None:
        self._data = io.BytesIO(data)
        self._fail_after = fail_after
        self.read_so_far = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        chunk = self._data.read(size)
        self.read_so_far += len(chunk)
        if self._fail_after is not None and self.read_so_far > self._fail_after:
            raise OverflowError("too big")
        return chunk


@pytest.fixture
def s3() -> Iterator[tuple[S3Storage, str]]:
    storage = S3Storage.from_settings(get_settings(), bucket=get_settings().s3_test_bucket)
    prefix = f"itest/{uuid.uuid4()}/"
    try:
        list(storage.list(prefix))
    except StorageError as exc:
        if isinstance(exc.__cause__, EndpointConnectionError):
            pytest.skip("Garage não está acessível")
        raise
    yield storage, prefix
    for obj in storage.list(prefix):
        storage.delete(obj.key)


def test_put_open_and_delete_round_trip_with_multipart_upload(s3):
    storage, prefix = s3
    data = bytes(range(256)) * (BIG // 256)
    key = f"{prefix}big"

    storage.put(key, NonSeekable(data), "application/pdf")
    reader = storage.open(key)
    try:
        head = reader.read(16)
        body = head + b"".join(reader.iter_chunks())
    finally:
        reader.close()

    assert (reader.size, body == data) == (len(data), True)
    storage.delete(key)
    with pytest.raises(ObjectNotFound):
        storage.open(key)


def test_missing_object_is_object_not_found_and_deleting_it_is_not_an_error(s3):
    storage, prefix = s3

    with pytest.raises(ObjectNotFound):
        storage.open(f"{prefix}missing")
    storage.delete(f"{prefix}missing")


def test_list_returns_only_objects_under_the_prefix(s3):
    storage, prefix = s3
    for name, size in (("a/1", 3), ("a/2", 5), ("b/1", 7)):
        storage.put(f"{prefix}{name}", io.BytesIO(b"x" * size), "text/plain")

    listed = list(storage.list(f"{prefix}a/"))

    assert [(obj.key, obj.size) for obj in listed] == [(f"{prefix}a/1", 3), (f"{prefix}a/2", 5)]
    assert all(abs(datetime.now(UTC) - obj.last_modified).total_seconds() < 300 for obj in listed)


def test_error_raised_by_the_stream_propagates_and_leaves_nothing_after_delete(s3):
    storage, prefix = s3
    key = f"{prefix}aborted"

    with pytest.raises(OverflowError):
        storage.put(key, NonSeekable(b"y" * BIG, fail_after=BIG // 2), "application/octet-stream")
    storage.delete(key)  # what the files service does after a failed put

    assert list(storage.list(prefix)) == []
