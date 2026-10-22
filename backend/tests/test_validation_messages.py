"""Portuguese 422 messages (app.api.errors) that never echo the received value."""

import uuid
from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, Strict, ValidationError

from app.api.errors import FALLBACK_MESSAGE, MESSAGES_BY_TYPE, _public_error
from app.schemas.common import IsoDate, NotNull

SECRET = "SEGREDO-7f3a"
TASKS_URL = "/api/tasks"


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class Inner(BaseModel):
    a: int


def _errors(annotation: Any, value: Any, *, json: bool = False, **config) -> list[dict]:
    """Real Pydantic errors for `value` validated as `annotation` (field `x`)."""
    model = type(
        "Probe",
        (BaseModel,),
        {"__annotations__": {"x": annotation}, "model_config": ConfigDict(**config)},
    )
    with pytest.raises(ValidationError) as exc_info:
        if json:
            model.model_validate_json(value)
        else:
            model.model_validate({"x": value} if value is not ... else {})
    return exc_info.value.errors()


CASES = [
    ("missing", lambda: _errors(int, ...), "Campo obrigatório."),
    ("string_type", lambda: _errors(str, [SECRET]), "Informe um texto."),
    ("extra_forbidden", lambda: _extra_errors(), "Campo não permitido."),
    ("enum", lambda: _errors(Color, SECRET), "Valor inválido. Use um destes: 'red' ou 'blue'."),
    (
        "literal_error",
        lambda: _errors(Literal["a", "b", "c"], SECRET),
        "Valor inválido. Use um destes: 'a', 'b' ou 'c'.",
    ),
    ("bool_parsing", lambda: _errors(bool, SECRET), "Informe true ou false."),
    ("int_parsing", lambda: _errors(int, SECRET), "Informe um número inteiro."),
    ("int_type", lambda: _errors(int, [SECRET]), "Informe um número inteiro."),
    (
        "date_parsing",
        lambda: _errors(Annotated[date, Strict()], f'{{"x": "2026-0{SECRET}"}}', json=True),
        "Informe uma data válida no formato AAAA-MM-DD.",
    ),
    (
        "date_from_datetime_parsing",
        lambda: _errors(date, SECRET),
        "Informe uma data válida no formato AAAA-MM-DD.",
    ),
    ("date_type", lambda: _errors(date, [SECRET]), "Informe uma data válida no formato AAAA-MM-DD."),
    ("uuid_parsing", lambda: _errors(uuid.UUID, SECRET), "Identificador inválido."),
    (
        "greater_than_equal",
        lambda: _errors(Annotated[int, Field(ge=1)], -987),
        "O valor deve ser maior ou igual a 1.",
    ),
    (
        "less_than_equal",
        lambda: _errors(Annotated[int, Field(le=100)], 98765),
        "O valor deve ser menor ou igual a 100.",
    ),
    (
        "string_too_long",
        lambda: _errors(Annotated[str, Field(max_length=3)], SECRET),
        "O texto deve ter no máximo 3 caracteres.",
    ),
    (
        "string_too_short",
        lambda: _errors(Annotated[str, Field(min_length=50)], SECRET),
        "O texto deve ter pelo menos 50 caracteres.",
    ),
    ("json_invalid", lambda: _errors(str, f'{{"x": {SECRET}', json=True), "JSON inválido."),
    (
        "model_attributes_type",
        lambda: _top_level_errors(Inner, SECRET, from_attributes=True),
        "Informe um objeto JSON.",
    ),
    ("dict_type", lambda: _errors(dict, [SECRET]), "Informe um objeto JSON."),
    ("list_type", lambda: _errors(list[int], SECRET), "Informe uma lista."),
]


def _top_level_errors(model: type[BaseModel], value: Any, **kwargs) -> list[dict]:
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(value, **kwargs)
    return exc_info.value.errors()


def _extra_errors() -> list[dict]:
    class Closed(BaseModel):
        model_config = ConfigDict(extra="forbid")

    with pytest.raises(ValidationError) as exc_info:
        Closed.model_validate({"x": SECRET})
    return exc_info.value.errors()


def test_every_mapped_type_has_a_case():
    assert {error_type for error_type, _, _ in CASES} == set(MESSAGES_BY_TYPE)


@pytest.mark.parametrize(("error_type", "make_errors", "message"), CASES, ids=[c[0] for c in CASES])
def test_pydantic_error_gets_portuguese_message_without_input(error_type, make_errors, message):
    errors = make_errors()
    assert errors[0]["type"] == error_type  # the probe really produces this error type

    public = _public_error(errors[0])

    assert public == {"type": error_type, "loc": list(errors[0]["loc"]), "msg": message}
    assert SECRET not in public["msg"]
    assert "-987" not in public["msg"] and "98765" not in public["msg"]


def test_unmapped_type_gets_generic_message():
    errors = _errors(float, SECRET)
    assert errors[0]["type"] not in MESSAGES_BY_TYPE

    assert _public_error(errors[0])["msg"] == FALLBACK_MESSAGE == "Valor inválido."


def test_template_with_missing_ctx_falls_back_to_generic_message():
    error = {"type": "less_than_equal", "loc": ("x",), "msg": "...", "input": SECRET, "ctx": {}}

    assert _public_error(error)["msg"] == FALLBACK_MESSAGE


def test_our_value_error_message_is_kept():
    errors = _errors(IsoDate, SECRET)

    assert _public_error(errors[0])["msg"] == "Informe uma data válida no formato AAAA-MM-DD."


def test_not_null_message():
    errors = _errors(Annotated[str, NotNull], None)

    assert _public_error(errors[0])["msg"] == "Este campo não pode ser nulo."


# --- through the API ---------------------------------------------------------------------------


@pytest.fixture
def headers(authenticate):
    return authenticate("ana@example.test")[1]


@pytest.mark.parametrize(
    ("request_kwargs", "loc", "message"),
    [
        ({"method": "GET", "url": f"{TASKS_URL}/{SECRET}"}, ["path", "task_id"], "Identificador inválido."),
        ({"method": "POST", "url": TASKS_URL, "json": {}}, ["body", "title"], "Campo obrigatório."),
        (
            {"method": "POST", "url": TASKS_URL, "json": {"title": "X", "owner": SECRET}},
            ["body", "owner"],
            "Campo não permitido.",
        ),
        (
            {"method": "POST", "url": TASKS_URL, "json": {"title": [SECRET]}},
            ["body", "title"],
            "Informe um texto.",
        ),
        (
            {"method": "POST", "url": TASKS_URL, "json": {"title": "X", "status": SECRET}},
            ["body", "status"],
            "Valor inválido. Use um destes: 'todo', 'doing' ou 'done'.",
        ),
        (
            {"method": "POST", "url": TASKS_URL, "json": {"title": "X", "due_date": SECRET}},
            ["body", "due_date"],
            "Informe uma data válida no formato AAAA-MM-DD.",
        ),
        (
            {"method": "POST", "url": TASKS_URL, "content": f'{{"title": "{SECRET}"'.encode()},
            None,
            "JSON inválido.",
        ),
        (
            {"method": "GET", "url": TASKS_URL, "params": {"limit": 1000}},
            ["query", "limit"],
            "O valor deve ser menor ou igual a 100.",
        ),
        (
            {"method": "GET", "url": TASKS_URL, "params": {"offset": -1}},
            ["query", "offset"],
            "O valor deve ser maior ou igual a 0.",
        ),
        (
            {"method": "GET", "url": TASKS_URL, "params": {"limit": SECRET}},
            ["query", "limit"],
            "Informe um número inteiro.",
        ),
        (
            {"method": "GET", "url": TASKS_URL, "params": {"overdue": SECRET}},
            ["query", "overdue"],
            "Informe true ou false.",
        ),
        (
            {"method": "GET", "url": TASKS_URL, "params": {"due_to": "1778371200"}},
            ["query", "due_to"],
            "Informe uma data válida no formato AAAA-MM-DD.",
        ),
    ],
    ids=[
        "uuid-path",
        "missing",
        "extra",
        "string-type",
        "enum",
        "date",
        "json-invalid",
        "le",
        "ge",
        "int",
        "bool",
        "timestamp-date",
    ],
)
def test_api_422_messages_are_portuguese_and_do_not_echo(client, headers, request_kwargs, loc, message):
    kwargs = dict(request_kwargs)
    if "content" in kwargs:
        kwargs["headers"] = {**headers, "Content-Type": "application/json"}
    else:
        kwargs["headers"] = headers

    response = client.request(**kwargs)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["msg"] == message
    if loc is not None:
        assert error["loc"] == loc
    assert SECRET not in response.text
    assert "1778371200" not in response.text


@pytest.mark.parametrize("field", ["title", "status", "priority"])
def test_patch_null_on_not_null_field_has_portuguese_message(
    client, headers, create_task, authenticate, field
):
    response = client.post(TASKS_URL, json={"title": "X"}, headers=headers)
    task_id = response.json()["id"]

    response = client.patch(f"{TASKS_URL}/{task_id}", json={field: None}, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {"type": "value_error", "loc": ["body", field], "msg": "Este campo não pode ser nulo."}
    ]
