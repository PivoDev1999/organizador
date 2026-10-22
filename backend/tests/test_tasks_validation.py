"""Input validation of POST/PATCH /api/tasks beyond the basic cases in test_tasks_crud.py."""

import json
import uuid

import pytest

TASKS_URL = "/api/tasks"
SECRET = "SEGREDO-7f3a"
NUL_MESSAGE = "O texto não pode conter o caractere nulo (\\x00)."
INVALID_TEXT_MESSAGE = "O texto contém caracteres inválidos."
JSON_HEADERS = {"Content-Type": "application/json"}


def task_url(task_id) -> str:
    return f"{TASKS_URL}/{task_id}"


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def ana_task(ana, create_task):
    return create_task(ana[0], "Intacta", description="Desc original")


def post_raw(client, headers, raw: bytes, url: str = TASKS_URL, method: str = "POST"):
    """Send a raw body: lets the test use JSON escapes such as \\u0000 and \\ud800 verbatim."""
    return client.request(method, url, content=raw, headers={**headers, **JSON_HEADERS})


def assert_422_at(response, loc: list, message: str | None = None) -> None:
    assert response.status_code == 422, response.text
    errors = response.json()["detail"]
    assert [error["loc"] for error in errors] == [loc]
    if message is not None:
        assert errors[0]["msg"] == message
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)


# --- title -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title", ["\t\n ", " ", "　 ", "\r\n"], ids=["tab-newline", "nbsp", "ideographic", "crlf"]
)
def test_create_title_with_only_unicode_whitespace_is_rejected(client, ana, title):
    response = client.post(TASKS_URL, json={"title": title}, headers=ana[1])

    assert_422_at(response, ["body", "title"], "Informe o título.")


def test_title_length_is_checked_after_trimming(client, ana):
    response = client.post(TASKS_URL, json={"title": f"   {'a' * 200}   "}, headers=ana[1])

    assert response.status_code == 201
    assert response.json()["title"] == "a" * 200


@pytest.mark.parametrize(
    ("title", "status_code"),
    [("😀" * 200, 201), ("😀" * 201, 422), ("ç" * 200, 201), ("ç" * 201, 422)],
    ids=["200-emoji", "201-emoji", "200-accented", "201-accented"],
)
def test_title_limit_counts_characters_not_bytes(client, ana, title, status_code):
    response = client.post(TASKS_URL, json={"title": title}, headers=ana[1])

    assert response.status_code == status_code, response.text
    if status_code == 201:
        # Stored in VARCHAR(200) without truncation: 200 multi-byte characters fit.
        task_id = response.json()["id"]
        assert client.get(task_url(task_id), headers=ana[1]).json()["title"] == title


@pytest.mark.parametrize(
    "title",
    ["Pão de queijo 🧀", "日本語のタスク", "👨‍👩‍👧 família", "Ação: café, maçã e jabuticaba", "é"],
    ids=["emoji", "cjk", "zwj-sequence", "accents", "combining-mark"],
)
def test_unicode_title_round_trips(client, ana, title):
    body = client.post(TASKS_URL, json={"title": title, "description": title}, headers=ana[1]).json()

    stored = client.get(task_url(body["id"]), headers=ana[1]).json()
    assert stored["title"] == title
    assert stored["description"] == title


@pytest.mark.parametrize(
    ("raw_title", "message"),
    [
        ('"a\\u0000b"', NUL_MESSAGE),
        ('"\\u0000"', NUL_MESSAGE),
        ('"\\ud800"', INVALID_TEXT_MESSAGE),
        ('"ok \\udfff"', INVALID_TEXT_MESSAGE),
    ],
    ids=["nul-inside", "only-nul", "lone-high-surrogate", "lone-low-surrogate"],
)
def test_create_title_with_nul_or_lone_surrogate_in_raw_json_is_422(client, ana, raw_title, message):
    response = post_raw(client, ana[1], f'{{"title": {raw_title}}}'.encode())

    assert_422_at(response, ["body", "title"], message)


@pytest.mark.parametrize(
    ("field", "raw_value", "message"),
    [
        ("title", '"a\\u0000b"', NUL_MESSAGE),
        ("title", '"\\ud800"', INVALID_TEXT_MESSAGE),
        ("description", '"a\\u0000b"', NUL_MESSAGE),
        ("description", '"\\ud800"', INVALID_TEXT_MESSAGE),
    ],
    ids=["title-nul", "title-surrogate", "description-nul", "description-surrogate"],
)
def test_patch_text_with_nul_or_lone_surrogate_is_422_and_task_unchanged(
    client, ana, ana_task, field, raw_value, message
):
    response = post_raw(
        client, ana[1], f'{{"{field}": {raw_value}}}'.encode(), task_url(ana_task.id), "PATCH"
    )

    assert_422_at(response, ["body", field], message)
    stored = client.get(task_url(ana_task.id), headers=ana[1]).json()
    assert (stored["title"], stored["description"]) == ("Intacta", "Desc original")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"title": "x", "status": "\\ud800"}',
        b'{"title": "x", "due_date": "\\ud800"}',
        b'{"title": "x", "\\ud800": 1}',
        b'{"title": "x", "description": "\\ud800\\u0000"}',
    ],
    ids=["surrogate-status", "surrogate-date", "surrogate-key", "surrogate-and-nul"],
)
def test_lone_surrogates_anywhere_never_cause_500(client, ana, raw):
    response = post_raw(client, ana[1], raw)

    assert response.status_code == 422
    response.json()  # the error body itself is valid JSON (no surrogate leaked into it)


def test_patch_title_limits(client, ana, ana_task):
    url = task_url(ana_task.id)

    too_long = client.patch(url, json={"title": "b" * 201}, headers=ana[1])
    assert_422_at(too_long, ["body", "title"], "O título deve ter no máximo 200 caracteres.")

    exact = client.patch(url, json={"title": "b" * 200}, headers=ana[1])
    assert exact.status_code == 200
    assert exact.json()["title"] == "b" * 200


@pytest.mark.parametrize("title", ["   ", "\t"], ids=["spaces", "tab"])
def test_patch_blank_title_is_rejected(client, ana, ana_task, title):
    response = client.patch(task_url(ana_task.id), json={"title": title}, headers=ana[1])

    assert_422_at(response, ["body", "title"], "Informe o título.")


# --- description -------------------------------------------------------------------------------


@pytest.mark.parametrize("description", ["", "   ", "\n\t"], ids=["empty", "spaces", "whitespace"])
def test_create_empty_or_blank_description_becomes_null(client, ana, description):
    body = client.post(TASKS_URL, json={"title": "X", "description": description}, headers=ana[1]).json()

    assert body["description"] is None


def test_patch_empty_description_clears_it(client, ana, ana_task):
    response = client.patch(task_url(ana_task.id), json={"description": ""}, headers=ana[1])

    assert response.status_code == 200
    assert client.get(task_url(ana_task.id), headers=ana[1]).json()["description"] is None


def test_description_is_trimmed(client, ana):
    body = client.post(
        TASKS_URL, json={"title": "X", "description": "  Ligar antes.\n"}, headers=ana[1]
    ).json()

    assert body["description"] == "Ligar antes."


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_description_with_exactly_5000_characters_is_accepted(client, ana, ana_task, method):
    payload = {"title": "X", "description": "d" * 5000}
    url = TASKS_URL if method == "POST" else task_url(ana_task.id)

    response = client.request(method, url, json=payload, headers=ana[1])

    assert response.status_code in (200, 201)
    assert response.json()["description"] == "d" * 5000


def test_description_limit_is_checked_after_trimming(client, ana):
    response = client.post(TASKS_URL, json={"title": "X", "description": f"  {'d' * 5000}  "}, headers=ana[1])

    assert response.status_code == 201


def test_patch_description_over_limit_is_rejected(client, ana, ana_task):
    response = client.patch(task_url(ana_task.id), json={"description": "d" * 5001}, headers=ana[1])

    assert_422_at(response, ["body", "description"], "A descrição deve ter no máximo 5000 caracteres.")


# --- status and priority -----------------------------------------------------------------------


ENUM_CASES = [
    ("status", "TODO"),
    ("status", "Done"),
    ("status", " todo"),
    ("status", ""),
    ("status", 1),
    ("priority", "HIGH"),
    ("priority", "Low"),
    ("priority", "medium "),
    ("priority", ""),
    ("priority", 3),
]
ENUM_IDS = [f"{field}-{value!r}" for field, value in ENUM_CASES]


@pytest.mark.parametrize(("field", "value"), ENUM_CASES, ids=ENUM_IDS)
def test_create_enum_values_are_case_sensitive_and_exact(client, ana, field, value):
    response = client.post(TASKS_URL, json={"title": "X", field: value}, headers=ana[1])

    assert_422_at(response, ["body", field])


@pytest.mark.parametrize(("field", "value"), ENUM_CASES, ids=ENUM_IDS)
def test_patch_enum_values_are_case_sensitive_and_exact(client, ana, ana_task, field, value):
    response = client.patch(task_url(ana_task.id), json={field: value}, headers=ana[1])

    assert_422_at(response, ["body", field])


@pytest.mark.parametrize("field", ["status", "priority", "title"])
def test_create_explicit_null_for_non_nullable_field_is_rejected(client, ana, field):
    payload = {"title": "X", field: None}

    response = client.post(TASKS_URL, json=payload, headers=ana[1])

    assert_422_at(response, ["body", field])


def test_patch_invalid_priority_is_rejected(client, ana, ana_task):
    response = client.patch(task_url(ana_task.id), json={"priority": "urgent"}, headers=ana[1])

    assert_422_at(response, ["body", "priority"])
    assert client.get(task_url(ana_task.id), headers=ana[1]).json()["priority"] == "medium"


# --- due_date ----------------------------------------------------------------------------------


INVALID_DATES = [
    "2026-13-01",
    "2026-02-30",
    "10/05/2026",
    "2026-5-1",
    "",
    "amanhã",
    "2026-05-10T10:30:00",
    True,
]
INVALID_DATE_IDS = [
    "month-13",
    "feb-30",
    "br-format",
    "no-padding",
    "empty",
    "word",
    "datetime-with-time",
    "bool",
]


@pytest.mark.parametrize("value", INVALID_DATES, ids=INVALID_DATE_IDS)
def test_create_invalid_due_date_is_rejected(client, ana, value):
    response = client.post(TASKS_URL, json={"title": "X", "due_date": value}, headers=ana[1])

    assert_422_at(response, ["body", "due_date"])


@pytest.mark.parametrize("value", INVALID_DATES, ids=INVALID_DATE_IDS)
def test_patch_invalid_due_date_is_rejected(client, ana, ana_task, value):
    response = client.patch(task_url(ana_task.id), json={"due_date": value}, headers=ana[1])

    assert_422_at(response, ["body", "due_date"])


@pytest.mark.parametrize(
    "value",
    ["2026-05-10T00:00:00", "2026-05-10T00:00:00Z", "2026-05-10T00:00:00-03:00", 1778371200, 0, "1778371200"],
    ids=["midnight-naive", "midnight-utc", "midnight-offset", "unix-timestamp", "zero", "numeric-string"],
)
def test_due_date_rejects_datetimes_and_timestamps(client, ana, value):
    response = client.post(TASKS_URL, json={"title": "X", "due_date": value}, headers=ana[1])

    assert response.status_code == 422


def test_patch_due_date_sets_and_null_clears(client, ana, ana_task):
    url = task_url(ana_task.id)

    assert (
        client.patch(url, json={"due_date": "2026-12-25"}, headers=ana[1]).json()["due_date"] == "2026-12-25"
    )
    assert client.get(url, headers=ana[1]).json()["due_date"] == "2026-12-25"

    assert client.patch(url, json={"due_date": None}, headers=ana[1]).json()["due_date"] is None
    assert client.get(url, headers=ana[1]).json()["due_date"] is None


@pytest.mark.parametrize("value", ["0001-01-01", "9999-12-31", "2028-02-29"], ids=["min", "max", "leap-day"])
def test_due_date_extremes_round_trip(client, ana, value):
    body = client.post(TASKS_URL, json={"title": "X", "due_date": value}, headers=ana[1]).json()

    assert client.get(task_url(body["id"]), headers=ana[1]).json()["due_date"] == value


# --- extra fields ------------------------------------------------------------------------------


EXTRA_FIELDS = {
    "completed_at": "2026-01-01T00:00:00Z",
    "user_id": str(uuid.uuid4()),
    "id": str(uuid.uuid4()),
    "created_at": "2020-01-01T00:00:00Z",
    "updated_at": "2020-01-01T00:00:00Z",
    "owner": "bia",
}


@pytest.mark.parametrize("field", ["created_at", "updated_at", "owner"])
def test_create_rejects_more_extra_fields(client, ana, field):
    response = client.post(TASKS_URL, json={"title": "X", field: EXTRA_FIELDS[field]}, headers=ana[1])

    assert_422_at(response, ["body", field])
    assert client.get(TASKS_URL, headers=ana[1]).json()["total"] == 0


@pytest.mark.parametrize("field", ["id", "created_at", "updated_at", "owner"])
def test_patch_rejects_more_extra_fields(client, ana, ana_task, field):
    before = client.get(task_url(ana_task.id), headers=ana[1]).json()

    response = client.patch(
        task_url(ana_task.id), json={"title": "Nova", field: EXTRA_FIELDS[field]}, headers=ana[1]
    )

    assert_422_at(response, ["body", field])
    # A valid field next to the extra one is not applied either.
    assert client.get(task_url(ana_task.id), headers=ana[1]).json() == before


def test_patch_with_extra_null_field_is_rejected(client, ana, ana_task):
    response = client.patch(task_url(ana_task.id), json={"completed_at": None}, headers=ana[1])

    assert_422_at(response, ["body", "completed_at"])


# --- invalid bodies ----------------------------------------------------------------------------


INVALID_BODIES = [
    b"[]",
    b'[{"title": "X"}]',
    b'"X"',
    b"42",
    b"true",
    b"null",
    b"",
    b"{bad",
    b'{"title": "X",}',
]
INVALID_BODY_IDS = [
    "empty-list",
    "list",
    "string",
    "number",
    "bool",
    "null",
    "empty",
    "broken",
    "trailing-comma",
]


@pytest.mark.parametrize("raw", INVALID_BODIES, ids=INVALID_BODY_IDS)
def test_create_with_invalid_body_is_422(client, ana, raw):
    response = post_raw(client, ana[1], raw)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "body"
    assert client.get(TASKS_URL, headers=ana[1]).json()["total"] == 0


@pytest.mark.parametrize("raw", INVALID_BODIES, ids=INVALID_BODY_IDS)
def test_patch_with_invalid_body_is_422(client, ana, ana_task, raw):
    response = post_raw(client, ana[1], raw, task_url(ana_task.id), "PATCH")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "body"


def test_create_with_non_json_content_type_is_422(client, ana):
    response = client.post(
        TASKS_URL, content=b'{"title": "X"}', headers={**ana[1], "Content-Type": "text/plain"}
    )

    assert response.status_code == 422


def test_create_with_form_body_is_422(client, ana):
    response = client.post(TASKS_URL, data={"title": "X"}, headers=ana[1])

    assert response.status_code == 422


# --- errors never echo the input ---------------------------------------------------------------


ECHO_PAYLOADS = [
    {"title": SECRET * 30},
    {"title": f"{SECRET}\x00"},
    {"title": "X", "description": SECRET * 500},
    {"title": "X", "description": f"{SECRET}\x00"},
    {"title": "X", "status": SECRET},
    {"title": "X", "priority": SECRET},
    {"title": "X", "due_date": SECRET},
    {"title": "X", "due_date": f"2026-05-10T{SECRET}"},
    {"title": "X", "completed_at": SECRET},
    {"title": "X", "user_id": SECRET},
    {"title": ["X", SECRET]},
    {"title": {"nested": SECRET}},
]
ECHO_IDS = [
    "long-title",
    "nul-title",
    "long-description",
    "nul-description",
    "status",
    "priority",
    "date",
    "datetime-like",
    "extra-field",
    "extra-user-id",
    "title-list",
    "title-object",
]


@pytest.mark.parametrize("payload", ECHO_PAYLOADS, ids=ECHO_IDS)
def test_create_422_never_echoes_input(client, ana, payload):
    response = client.post(TASKS_URL, json=payload, headers=ana[1])

    assert response.status_code == 422
    assert SECRET not in response.text


@pytest.mark.parametrize("payload", ECHO_PAYLOADS, ids=ECHO_IDS)
def test_patch_422_never_echoes_input(client, ana, ana_task, payload):
    payload = {key: value for key, value in payload.items() if not (key == "title" and value == "X")}

    response = client.patch(task_url(ana_task.id), json=payload, headers=ana[1])

    assert response.status_code == 422
    assert SECRET not in response.text


def test_broken_json_error_does_not_echo_input(client, ana):
    response = post_raw(client, ana[1], f'{{"title": "{SECRET}", oops}}'.encode())

    assert response.status_code == 422
    assert SECRET not in response.text


@pytest.mark.parametrize(
    "params",
    [
        {"q": SECRET * 20},
        {"q": f"{SECRET}\x00"},
        {"status": SECRET},
        {"priority": SECRET},
        {"sort": SECRET},
        {"due_from": SECRET},
        {"overdue": SECRET},
        {"limit": SECRET},
        {"offset": SECRET},
    ],
    ids=["long-q", "nul-q", "status", "priority", "sort", "date", "bool", "limit", "offset"],
)
def test_list_422_never_echoes_query(client, ana, params):
    response = client.get(TASKS_URL, params=params, headers=ana[1])

    assert response.status_code == 422
    assert SECRET not in response.text


def test_error_body_is_plain_json(client, ana):
    response = client.post(TASKS_URL, json={"title": ""}, headers=ana[1])

    assert response.headers["content-type"] == "application/json"
    assert json.loads(response.content)["detail"][0]["type"] == "value_error"
