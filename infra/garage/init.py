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
import urllib.parse
import urllib.request

ADMIN_URL = os.environ["GARAGE_ADMIN_URL"].rstrip("/")
ADMIN_TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
CAPACITY = os.environ.get("GARAGE_CAPACITY", "10G")
ACCESS_KEY_ID = os.environ["S3_ACCESS_KEY_ID"]
SECRET_ACCESS_KEY = os.environ["S3_SECRET_ACCESS_KEY"]
BUCKET = os.environ["S3_BUCKET"]
ZONE = "home"

SERVER_ERROR_RETRIES = 5

UNITS = {"": 1, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}


class NotFound(Exception):
    pass


class ServerError(RuntimeError):
    """5xx from Garage: usually transient while the node is starting."""


def api(method: str, endpoint: str, body: dict | None = None, query: dict | None = None) -> dict:
    url = f"{ADMIN_URL}/v2/{endpoint}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"},
    )
    # 5xx is retried: right after ApplyClusterLayout the new layout may still be propagating.
    for attempt in range(SERVER_ERROR_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read()
            return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as error:
            message = f"{method} {endpoint} -> {error.code}: {error.read().decode()}"
            if error.code == 404:
                raise NotFound(endpoint) from error
            if error.code in (401, 403):
                sys.exit(f"Garage rejected the admin token ({message}). Check GARAGE_ADMIN_TOKEN in .env.")
            if error.code < 500 or attempt == SERVER_ERROR_RETRIES - 1:
                raise (ServerError if error.code >= 500 else RuntimeError)(message) from error
            time.sleep(2)
    raise AssertionError("unreachable")


def validate_env() -> None:
    placeholders = {
        "GARAGE_ADMIN_TOKEN": ADMIN_TOKEN,
        "S3_SECRET_ACCESS_KEY": SECRET_ACCESS_KEY,
    }
    problems = [name for name, value in placeholders.items() if value in ("", "change-me")]
    if not re.fullmatch(r"GK[0-9a-f]{24}", ACCESS_KEY_ID) or set(ACCESS_KEY_ID[2:]) == {"0"}:
        problems.append('S3_ACCESS_KEY_ID (use: echo "GK$(openssl rand -hex 12)")')
    if not re.fullmatch(r"[0-9a-f]{64}", SECRET_ACCESS_KEY):
        problems.append("S3_SECRET_ACCESS_KEY (use: openssl rand -hex 32)")
    if problems:
        sys.exit("Invalid or placeholder values in .env: " + ", ".join(dict.fromkeys(problems)))


def parse_capacity(value: str) -> int:
    match = re.fullmatch(r"(\d+)\s*([KMGT]?)B?", value.strip().upper())
    if not match:
        raise ValueError(f"Invalid GARAGE_CAPACITY: {value!r}")
    return int(match.group(1)) * UNITS[match.group(2)]


def wait_for_admin_api() -> dict:
    for _ in range(30):
        try:
            return api("GET", "GetClusterStatus")
        # HTTPError never reaches here (api() converts it), so URLError means "cannot connect".
        except (urllib.error.URLError, ConnectionError, ServerError):
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
        key = api("GET", "GetKeyInfo", query={"id": ACCESS_KEY_ID, "showSecretKey": "true"})
    except NotFound:
        api(
            "POST",
            "ImportKey",
            {"accessKeyId": ACCESS_KEY_ID, "secretAccessKey": SECRET_ACCESS_KEY, "name": "organizador-api"},
        )
        print(f"key: {ACCESS_KEY_ID} imported")
        return
    # Garage keeps the secret it was imported with; a changed .env would break every S3 call later.
    if key.get("secretAccessKey") != SECRET_ACCESS_KEY:
        sys.exit(
            f"key: {ACCESS_KEY_ID} exists with a different secret than S3_SECRET_ACCESS_KEY. "
            "Restore the old secret in .env, or delete the key "
            f"(docker compose exec garage /garage key delete --yes {ACCESS_KEY_ID}) "
            "and run garage-init again."
        )
    print(f"key: {ACCESS_KEY_ID} already exists (secret matches)")


def ensure_bucket() -> None:
    try:
        bucket = api("GET", "GetBucketInfo", query={"globalAlias": BUCKET})
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
            # No "owner": the API key must not be able to change or delete the bucket itself.
            "permissions": {"read": True, "write": True, "owner": False},
        },
    )
    # AllowBucketKey only adds flags, so revoke "owner" explicitly in case an older run granted it.
    api(
        "POST",
        "DenyBucketKey",
        {
            "bucketId": bucket["id"],
            "accessKeyId": ACCESS_KEY_ID,
            "permissions": {"read": False, "write": False, "owner": True},
        },
    )
    print(f"bucket: read/write (no owner) granted to {ACCESS_KEY_ID}")


def main() -> None:
    validate_env()
    status = wait_for_admin_api()
    ensure_layout(status)
    ensure_key()
    ensure_bucket()
    print("garage-init: done")


if __name__ == "__main__":
    main()
