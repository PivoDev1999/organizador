"""Pure rules for uploaded files: content type, file name and download headers.

Downloads come from the same origin as the frontend, so a stored HTML or SVG opened in the browser
would run scripts with the user's session (XSS). The rules:

- On upload, the type is detected by the first bytes (signature) for the few formats the browser may
  show: JPEG, PNG, GIF, WebP and PDF. When detected, that is the stored `content_type`, whatever the
  client said. Otherwise the client's type is kept if it is a well-formed `type/subtype` (parameters
  dropped), except that it can never claim one of the inline types without the matching bytes: then,
  and for anything malformed or missing, it becomes `application/octet-stream`.
- On download, `inline` is honored only if the stored type is one of those formats AND the first bytes
  of the object still match it. Anything else goes out as `attachment` + `application/octet-stream`.
  SVG and HTML are never inline. Every download carries `nosniff` and a CSP sandbox.
"""

import re
import unicodedata
from urllib.parse import quote

OCTET_STREAM = "application/octet-stream"
DEFAULT_FILE_NAME = "arquivo"
FILE_NAME_MAX_LENGTH = 200  # files.original_name is VARCHAR(255); leave room to spare
EXTENSION_MAX_LENGTH = 16
CONTENT_TYPE_MAX_LENGTH = 255  # files.content_type is VARCHAR(255)

# Enough for every signature below.
SNIFF_LENGTH = 16

JPEG, PNG, GIF, WEBP, PDF = "image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"
# The only types that may be shown inline by the browser.
INLINE_TYPES = frozenset({JPEG, PNG, GIF, WEBP, PDF})

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # No scripts, no plugins, unique origin: even an HTML that slipped through cannot reach the app.
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-store",
}

# RFC 7230 token characters, lower-case (the type is lower-cased first).
_TOKEN = r"[a-z0-9!#$%&'*+.^_`|~-]+"
_MEDIA_TYPE = re.compile(rf"({_TOKEN})/({_TOKEN})")
# Characters removed from names: path separators and those Windows refuses in a file name.
_UNSAFE_NAME_CHARS = re.compile(r'[/\\:*?"<>|]')
_ASCII_UNSAFE = re.compile(r"[^A-Za-z0-9 ._()\[\]+,-]")
_EXTENSION = re.compile(rf"[A-Za-z0-9]{{1,{EXTENSION_MAX_LENGTH}}}")
# Unicode categories removed: controls (C0/C1, CR, LF, NUL), format (bidi overrides), surrogates,
# private use, unassigned, line and paragraph separators.
_DROPPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def detect_type(head: bytes) -> str | None:
    """The inline-safe type the first bytes prove, or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith((b"GIF87a", b"GIF89a")):
        return GIF
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    if head.startswith(b"%PDF-"):
        return PDF
    return None


def clean_media_type(value: str | None) -> str | None:
    """`type/subtype` in lower case, parameters dropped; None when malformed or missing."""
    if not value:
        return None
    essence = value.split(";", 1)[0].strip().lower()
    if len(essence) > CONTENT_TYPE_MAX_LENGTH or not _MEDIA_TYPE.fullmatch(essence):
        return None
    return essence


def stored_content_type(head: bytes, declared: str | None) -> str:
    """The `content_type` to store for a file starting with `head` (see the module docstring)."""
    detected = detect_type(head)
    if detected:
        return detected
    cleaned = clean_media_type(declared)
    if cleaned is None or cleaned in INLINE_TYPES:
        return OCTET_STREAM
    return cleaned


def can_inline(content_type: str, head: bytes) -> bool:
    """Whether a download may go inline: an inline-safe type that the object's bytes confirm."""
    return content_type in INLINE_TYPES and detect_type(head) == content_type


def _truncate(name: str) -> str:
    if len(name) <= FILE_NAME_MAX_LENGTH:
        return name
    stem, dot, extension = name.rpartition(".")
    if dot and stem and len(extension) <= EXTENSION_MAX_LENGTH:
        keep = FILE_NAME_MAX_LENGTH - len(extension) - 1
        return f"{stem[:keep].rstrip()}.{extension}"
    return name[:FILE_NAME_MAX_LENGTH].rstrip()


def sanitize_file_name(name: str | None) -> str:
    """A display/download name safe for headers and file systems.

    No path separators, quotes, controls (NUL, CR, LF), bidi overrides or Windows-reserved characters;
    whitespace collapsed; no leading/trailing dots or spaces (hidden files, Windows); at most
    FILE_NAME_MAX_LENGTH characters, keeping the extension. Empty becomes DEFAULT_FILE_NAME.
    """
    if not name:
        return DEFAULT_FILE_NAME
    # Lone surrogates (undecodable bytes) become "?" (then "_") instead of breaking the DB or the header.
    name = unicodedata.normalize("NFC", name.encode("utf-8", "replace").decode("utf-8"))
    name = "".join(
        " " if char.isspace() else char
        for char in name
        if char.isspace() or unicodedata.category(char) not in _DROPPED_CATEGORIES
    )
    name = _UNSAFE_NAME_CHARS.sub("_", name)
    name = " ".join(name.split()).strip(" .")
    name = _truncate(name).strip(" .")
    return name or DEFAULT_FILE_NAME


def _to_ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(_ASCII_UNSAFE.sub("_", text).split()).strip(" .")


def ascii_file_name(name: str) -> str:
    """ASCII fallback for the plain `filename=` parameter (accents dropped, the rest replaced).

    A name with nothing readable left keeps its extension: "文件.pdf" -> "arquivo.pdf".
    """
    stem, dot, extension = name.rpartition(".")
    if not (dot and stem and _EXTENSION.fullmatch(extension)):
        stem, extension = name, ""
    ascii_stem = _to_ascii(stem)
    if not any(char.isalnum() for char in ascii_stem):
        ascii_stem = DEFAULT_FILE_NAME
    return f"{ascii_stem}.{extension}" if extension else ascii_stem


def content_disposition(name: str, *, inline: bool) -> str:
    """`inline|attachment; filename="ascii"; filename*=UTF-8''percent-encoded` (RFC 6266 / 5987)."""
    safe = sanitize_file_name(name)
    disposition = "inline" if inline else "attachment"
    return f"{disposition}; filename=\"{ascii_file_name(safe)}\"; filename*=UTF-8''{quote(safe, safe='')}"
