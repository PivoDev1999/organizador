"""S3 client of the backup (Garage), configured like the API's (backend/app/core/storage.py).

Not imported from the backend on purpose: `app.core.storage` depends on `app.core.config` (pydantic-settings
and every setting of the API, SECRET_KEY included). The backup image only gets the S3 variables and needs
four operations: list, download, upload and delete.
"""

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError

CHUNK_SIZE = 1024 * 1024
MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024
NOT_FOUND_CODES = frozenset({"NoSuchKey", "404", "NotFound"})


class ObjectGone(Exception):
    """The object was listed but deleted before it could be read."""


@dataclass(frozen=True)
class RemoteObject:
    key: str
    size: int
    etag: str


@dataclass(frozen=True)
class Downloaded:
    size: int
    sha256: str
    content_type: str


def _is_not_found(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return error.get("Code") in NOT_FOUND_CODES or status == 404


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


class Bucket:
    def __init__(self) -> None:
        self.name = os.environ["S3_BUCKET"]
        self._client = boto3.client(
            "s3",
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            region_name=os.environ.get("S3_REGION", "garage"),
            aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=5,
                read_timeout=60,
                retries={"max_attempts": 5, "mode": "standard"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        self._transfer = TransferConfig(
            multipart_threshold=MULTIPART_CHUNK_SIZE,
            multipart_chunksize=MULTIPART_CHUNK_SIZE,
            use_threads=False,
        )

    def list(self) -> Iterator[RemoteObject]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.name):
            for item in page.get("Contents", []):
                yield RemoteObject(item["Key"], item["Size"], item.get("ETag", "").strip('"'))

    def download(self, key: str, dest: Path) -> Downloaded:
        """Stream the object to `dest` (fsynced), hashing it on the way."""
        try:
            response = self._client.get_object(Bucket=self.name, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectGone(key) from exc
            raise
        digest = hashlib.sha256()
        size = 0
        body = response["Body"]
        try:
            with dest.open("wb") as out:
                for chunk in body.iter_chunks(CHUNK_SIZE):
                    digest.update(chunk)
                    out.write(chunk)
                    size += len(chunk)
                out.flush()
                os.fsync(out.fileno())
        finally:
            body.close()
        if size != response["ContentLength"]:
            raise OSError(f"short read of object {key}: {size} of {response['ContentLength']} bytes")
        content_type = response.get("ContentType") or "application/octet-stream"
        return Downloaded(size=size, sha256=digest.hexdigest(), content_type=content_type)

    def upload(self, path: Path, key: str, content_type: str) -> None:
        self._client.upload_file(
            str(path), self.name, key, ExtraArgs={"ContentType": content_type}, Config=self._transfer
        )

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._client.put_object(Bucket=self.name, Key=key, Body=data, ContentType=content_type)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.name, Key=key)


def md5_of(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
