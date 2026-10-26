"""Object storage (Garage, via the S3 API) behind a small interface.

The API talks to `Storage` only; `S3Storage` is the real implementation and the tests use the in-memory
`FakeStorage` (tests/fakes.py). The dependency `get_storage` builds a single `S3Storage` per process, and
the tests override it.

Every method raises `StorageError` (or its subclass `ObjectNotFound`) instead of library exceptions, so
the services can turn them into clear domain errors.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import BinaryIO, Protocol

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings

# Size of each block streamed to the client on download.
DOWNLOAD_CHUNK_SIZE = 64 * 1024
# Above this size the upload goes in multipart parts of this size. Without threads, at most one part
# is in memory at a time.
MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024

MAX_POOL_CONNECTIONS = 40

NOT_FOUND_CODES = frozenset({"NoSuchKey", "404", "NotFound"})


class StorageError(Exception):
    """The storage failed (connection, permissions, unexpected response). Details go to the log only."""


class ObjectNotFound(StorageError):
    """The key does not exist in the bucket."""


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    last_modified: datetime


class ObjectReader(Protocol):
    """An open object: read the first bytes with `read`, then the rest in blocks with `iter_chunks`."""

    size: int

    def read(self, size: int) -> bytes: ...

    def iter_chunks(self) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class Storage(Protocol):
    bucket: str

    def put(self, key: str, stream: BinaryIO, content_type: str) -> None:
        """Store everything `stream.read()` returns. `stream.read(n)` must return exactly n bytes until
        the end (a short read means "end of stream" to s3transfer). If reading fails, the exception
        propagates (a partial object may be left behind: the caller deletes the key)."""
        ...

    def open(self, key: str) -> ObjectReader:
        """Open the object for streaming. Raises ObjectNotFound when the key does not exist."""
        ...

    def delete(self, key: str) -> None:
        """Delete the object. Deleting a missing key is not an error."""
        ...

    def list(self, prefix: str = "") -> Iterator[ObjectInfo]:
        """Every object whose key starts with `prefix` (paginated lazily)."""
        ...


class _S3ObjectReader:
    def __init__(self, body, size: int) -> None:
        self._body = body
        self.size = size

    def read(self, size: int) -> bytes:
        try:
            return self._body.read(size)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError("read failed") from exc

    def iter_chunks(self) -> Iterator[bytes]:
        try:
            yield from self._body.iter_chunks(DOWNLOAD_CHUNK_SIZE)
        except (BotoCoreError, ClientError, OSError) as exc:
            raise StorageError("read failed") from exc

    def close(self) -> None:
        self._body.close()  # idempotent


def _is_not_found(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error.get("Code") in NOT_FOUND_CODES or status == 404


class S3Storage:
    """Storage on any S3-compatible server; here Garage, with path-style addressing
    (`http://host:3900/bucket/key`: Garage has no per-bucket DNS names on the home network)."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
    ) -> None:
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 3, "mode": "standard"},
                # A download holds one connection while it streams. 40 = anyio's default thread limit,
                # which already caps how many sync endpoints (and streams) run at once.
                max_pool_connections=MAX_POOL_CONNECTIONS,
                # Checksums only when the operation requires them: keeps uploads compatible with S3
                # servers that do not implement every flexible-checksum algorithm.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        self._transfer = TransferConfig(
            multipart_threshold=MULTIPART_CHUNK_SIZE,
            multipart_chunksize=MULTIPART_CHUNK_SIZE,
            use_threads=False,
        )

    @classmethod
    def from_settings(cls, settings: Settings, *, bucket: str | None = None) -> "S3Storage":
        return cls(
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            bucket=bucket or settings.s3_bucket,
        )

    def put(self, key: str, stream: BinaryIO, content_type: str) -> None:
        try:
            self._client.upload_fileobj(
                stream, self.bucket, key, ExtraArgs={"ContentType": content_type}, Config=self._transfer
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("put failed") from exc
        # Anything else (the size limit of the reader above all) propagates unchanged.

    def open(self, key: str) -> _S3ObjectReader:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFound(key) from exc
            raise StorageError("get failed") from exc
        except BotoCoreError as exc:
            raise StorageError("get failed") from exc
        return _S3ObjectReader(response["Body"], response["ContentLength"])

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("delete failed") from exc

    def list(self, prefix: str = "") -> Iterator[ObjectInfo]:
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    yield ObjectInfo(item["Key"], item["Size"], item["LastModified"])
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("list failed") from exc


@lru_cache
def _default_storage() -> S3Storage:
    return S3Storage.from_settings(get_settings())


def get_storage() -> Storage:
    """FastAPI dependency. One client per process (boto3 clients are thread-safe); tests override it."""
    return _default_storage()
