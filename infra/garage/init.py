"""Bootstrap Garage through its Admin API v2: node layout, S3 key and bucket.

Idempotent: every step checks the current state before changing anything.
Uses only the standard library so the job runs offline on a stock Python image.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ADMIN_URL = os.environ["GARAGE_ADMIN_URL"].rstrip("/")
ADMIN_TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
CAPACITY = os.environ.get("GARAGE_CAPACITY", "10G")
ACCESS_KEY_ID = os.environ["S3_ACCESS_KEY_ID"]
SECRET_ACCESS_KEY = os.environ["S3_SECRET_ACCESS_KEY"]
BUCKET = os.environ["S3_BUCKET"]
ZONE = "home"

UNITS = {"": 1, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


class NotFound(Exception):
    pass


def api(method: str, endpoint: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{ADMIN_URL}/v2/{endpoint}",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise NotFound(endpoint) from error
        raise RuntimeError(f"{method} {endpoint} -> {error.code}: {error.read().decode()}") from error
    return json.loads(payload) if payload else {}


def parse_capacity(value: str) -> int:
    match = re.fullmatch(r"(\d+)\s*([KMGT]?)B?", value.strip().upper())
    if not match:
        raise ValueError(f"Invalid GARAGE_CAPACITY: {value!r}")
    return int(match.group(1)) * UNITS[match.group(2)]


def wait_for_admin_api() -> dict:
    for _ in range(30):
        try:
            return api("GET", "GetClusterStatus")
        except (urllib.error.URLError, ConnectionError, RuntimeError):
            time.sleep(2)
    sys.exit("Garage admin API did not become available")


def ensure_layout(status: dict) -> None:
    layout = api("GET", "GetClusterLayout")
    if layout["roles"]:
        print(f"layout: already applied (version {layout['version']})")
        return
    node_id = status["nodes"][0]["id"]
    api(
        "POST",
        "UpdateClusterLayout",
        {"roles": [{"id": node_id, "zone": ZONE, "capacity": parse_capacity(CAPACITY), "tags": []}]},
    )
    api("POST", "ApplyClusterLayout", {"version": layout["version"] + 1})
    print(f"layout: node {node_id[:16]} assigned to zone '{ZONE}' with {CAPACITY}")


def ensure_key() -> None:
    try:
        api("GET", f"GetKeyInfo?id={ACCESS_KEY_ID}")
        print(f"key: {ACCESS_KEY_ID} already exists")
    except NotFound:
        api(
            "POST",
            "ImportKey",
            {"accessKeyId": ACCESS_KEY_ID, "secretAccessKey": SECRET_ACCESS_KEY, "name": "organizador-api"},
        )
        print(f"key: {ACCESS_KEY_ID} imported")


def ensure_bucket() -> None:
    try:
        bucket = api("GET", f"GetBucketInfo?globalAlias={BUCKET}")
        print(f"bucket: '{BUCKET}' already exists")
    except NotFound:
        bucket = api("POST", "CreateBucket", {"globalAlias": BUCKET})
        print(f"bucket: '{BUCKET}' created")
    api(
        "POST",
        "AllowBucketKey",
        {
            "bucketId": bucket["id"],
            "accessKeyId": ACCESS_KEY_ID,
            "permissions": {"read": True, "write": True, "owner": True},
        },
    )
    print(f"bucket: read/write granted to {ACCESS_KEY_ID}")


def main() -> None:
    status = wait_for_admin_api()
    ensure_layout(status)
    ensure_key()
    ensure_bucket()
    print("garage-init: done")


if __name__ == "__main__":
    main()
