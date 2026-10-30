"""In-memory test doubles."""

from collections.abc import Iterator
from datetime import datetime
from typing import BinaryIO

from app.core import clock
from app.core.storage import DOWNLOAD_CHUNK_SIZE, ObjectInfo, ObjectNotFound, StorageError

FAKE_BUCKET = "fake-bucket"


class _FakeReader:
    def __init__(self, data: bytes, chunk_size: int) -> None:
        self._data = data
        self._position = 0
        self._chunk_size = chunk_size
        self.size = len(data)
        self.closed = False

    def read(self, size: int) -> bytes:
        chunk = self._data[self._position : self._position + size]
        self._position += len(chunk)
        return chunk

    def iter_chunks(self) -> Iterator[bytes]:
        while chunk := self.read(self._chunk_size):
            yield chunk

    def close(self) -> None:
        self.closed = True


class FakeStorage:
    """`Storage` in a dict. Set `fail_put`, `fail_open`, `fail_delete` or `fail_ping` to simulate a broken
    server.

    `put` writes as it reads, block by block, so an upload interrupted midway leaves a partial object
    behind, like an S3 multipart upload: the code under test must clean it up. Like s3transfer, it takes
    a short read as the end of the stream.
    """

    def __init__(self, bucket: str = FAKE_BUCKET, chunk_size: int = DOWNLOAD_CHUNK_SIZE) -> None:
        self.bucket = bucket
        self.chunk_size = chunk_size
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.modified: dict[str, datetime] = {}
        self.deleted: list[str] = []
        self.readers: list[_FakeReader] = []
        self.fail_put = self.fail_open = self.fail_delete = self.fail_ping = False

    def put(self, key: str, stream: BinaryIO, content_type: str) -> None:
        if self.fail_put:
            raise StorageError("put failed (fake)")
        self.objects[key] = b""
        self.content_types[key] = content_type
        self.modified[key] = clock.now_utc()
        while chunk := stream.read(self.chunk_size):
            self.objects[key] += chunk
            if len(chunk) < self.chunk_size:
                break  # like s3transfer: a short read is the end of the stream

    def open(self, key: str) -> _FakeReader:
        if self.fail_open:
            raise StorageError("open failed (fake)")
        if key not in self.objects:
            raise ObjectNotFound(key)
        reader = _FakeReader(self.objects[key], self.chunk_size)
        self.readers.append(reader)
        return reader

    def delete(self, key: str) -> None:
        if self.fail_delete:
            raise StorageError("delete failed (fake)")
        self.deleted.append(key)
        self.objects.pop(key, None)
        self.content_types.pop(key, None)
        self.modified.pop(key, None)

    def list(self, prefix: str = "") -> Iterator[ObjectInfo]:
        for key in sorted(self.objects):
            if key.startswith(prefix):
                yield ObjectInfo(key, len(self.objects[key]), self.modified[key])

    def ping(self) -> None:
        if self.fail_ping:
            raise StorageError("ping failed (fake)")
