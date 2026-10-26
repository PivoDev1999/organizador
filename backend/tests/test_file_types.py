import pytest

from app.core.file_types import FILE_NAME_MAX_LENGTH, sanitize_file_name, stored_content_type
from tests.helpers import JPEG, SVG


@pytest.mark.parametrize(
    ("head", "declared", "expected"),
    [
        (JPEG, None, "image/jpeg"),
        (SVG, "image/svg+xml", "image/svg+xml"),
        (b"a;b", "Text/CSV; charset=utf-8", "text/csv"),
        (b"abc", "text/html\r\nX-Evil: 1", "application/octet-stream"),
    ],
    ids=[
        "jpeg-undeclared",
        "svg-kept-as-declared",
        "parameters-dropped",
        "header-injection",
    ],
)
def test_stored_content_type(head, declared, expected):
    assert stored_content_type(head, declared) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../../etc/passwd", "_.._etc_passwd"),
        ('C:\\docs\\"nota"\r\n.txt', "C__docs__nota_ .txt"),
        ("fatura\u202efdp.exe", "faturafdp.exe"),
        ("a\x00b\udcff.txt", "ab_.txt"),
        (" .. ", "arquivo"),
    ],
    ids=["path", "quotes-backslash-crlf", "bidi-override", "nul-surrogate", "blank"],
)
def test_sanitize_file_name(name, expected):
    assert sanitize_file_name(name) == expected


def test_long_file_name_is_truncated_keeping_the_extension():
    name = sanitize_file_name("a" * 500 + ".jpeg")

    assert (len(name), name[-5:]) == (FILE_NAME_MAX_LENGTH, ".jpeg")
