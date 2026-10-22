from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import clock

TASKS_URL = "/api/tasks"
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def list_titles(client, ana):
    def _list(**params) -> list[str]:
        response = client.get(TASKS_URL, params=params, headers=ana[1])
        assert response.status_code == 200, response.text
        return [item["title"] for item in response.json()["items"]]

    return _list


@pytest.fixture
def make(ana, create_task):
    """Create tasks for Ana with increasing created_at, so creation order is deterministic."""
    counter = iter(range(1000))

    def _make(title: str, **fields):
        fields.setdefault("created_at", BASE + timedelta(minutes=next(counter)))
        return create_task(ana[0], title, **fields)

    return _make


def test_list_returns_page_of_own_tasks_only(client, ana, authenticate, create_task, make):
    make("Minha")
    bia, _ = authenticate("bia@example.test")
    create_task(bia, "Da Bia")

    response = client.get(TASKS_URL, headers=ana[1])

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert [item["title"] for item in body["items"]] == ["Minha"]
    assert (body["total"], body["limit"], body["offset"]) == (1, 20, 0)
    assert "user_id" not in body["items"][0]


def test_list_empty(client, ana):
    assert client.get(TASKS_URL, headers=ana[1]).json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


# --- filters -----------------------------------------------------------------------------------


def test_filter_by_single_and_multiple_status(make, list_titles):
    make("A fazer")
    make("Fazendo", status="doing")
    make("Feita", status="done")

    assert list_titles(status="doing") == ["Fazendo"]
    assert sorted(list_titles(status=["todo", "doing"])) == ["A fazer", "Fazendo"]


def test_filter_by_single_and_multiple_priority(make, list_titles):
    make("Baixa", priority="low")
    make("Média", priority="medium")
    make("Alta", priority="high")

    assert list_titles(priority="high") == ["Alta"]
    assert sorted(list_titles(priority=["low", "high"])) == ["Alta", "Baixa"]


@pytest.mark.parametrize(
    "params",
    [
        {"status": "archived"},
        {"status": ["todo", "nope"]},
        {"priority": "urgent"},
        {"sort": "title"},
        {"due_from": "ontem"},
        {"overdue": "talvez"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"q": "a\x00b"},
        {"q": "a" * 201},
    ],
    ids=[
        "bad-status",
        "one-bad-status",
        "bad-priority",
        "bad-sort",
        "bad-date",
        "bad-bool",
        "limit-zero",
        "limit-too-big",
        "negative-offset",
        "nul-in-q",
        "long-q",
    ],
)
def test_invalid_query_params_are_rejected(client, ana, params):
    response = client.get(TASKS_URL, params=params, headers=ana[1])

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors[0]["loc"][0] == "query"
    assert all("input" not in error for error in errors)


def test_due_range_is_inclusive(make, list_titles):
    make("Dia 9", due_date=date(2026, 5, 9))
    make("Dia 10", due_date=date(2026, 5, 10))
    make("Dia 15", due_date=date(2026, 5, 15))
    make("Dia 16", due_date=date(2026, 5, 16))
    make("Sem prazo")

    assert sorted(list_titles(due_from="2026-05-10", due_to="2026-05-15")) == ["Dia 10", "Dia 15"]
    assert sorted(list_titles(due_from="2026-05-15")) == ["Dia 15", "Dia 16"]
    assert sorted(list_titles(due_to="2026-05-09")) == ["Dia 9"]
    assert list_titles(due_from="2026-05-10", due_to="2026-05-10") == ["Dia 10"]


def test_due_from_after_due_to_is_rejected(client, ana):
    response = client.get(
        TASKS_URL, params={"due_from": "2026-05-11", "due_to": "2026-05-10"}, headers=ana[1]
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == (
        "A data inicial (due_from) não pode ser posterior à data final (due_to)."
    )


@pytest.fixture
def freeze_now(monkeypatch):
    def _freeze(moment: datetime) -> None:
        monkeypatch.setattr(clock, "now_utc", lambda: moment)

    return _freeze


def test_overdue_lists_open_tasks_due_before_today(make, list_titles, freeze_now, override_settings):
    override_settings(app_timezone="America/Sao_Paulo")
    freeze_now(datetime(2026, 5, 10, 15, 0, tzinfo=UTC))  # 12:00 in São Paulo
    make("Ontem", due_date=date(2026, 5, 9))
    make("Ontem fazendo", due_date=date(2026, 5, 9), status="doing")
    make("Ontem feita", due_date=date(2026, 5, 9), status="done")
    make("Hoje", due_date=date(2026, 5, 10))
    make("Sem prazo")

    assert sorted(list_titles(overdue="true")) == ["Ontem", "Ontem fazendo"]


def test_overdue_false_does_not_filter(make, list_titles, freeze_now):
    freeze_now(datetime(2026, 5, 10, 15, 0, tzinfo=UTC))
    make("Atrasada", due_date=date(2026, 5, 1))
    make("No prazo", due_date=date(2026, 5, 20))

    assert sorted(list_titles(overdue="false")) == ["Atrasada", "No prazo"]


def test_overdue_combines_with_other_filters(make, list_titles, freeze_now):
    freeze_now(datetime(2026, 5, 10, 15, 0, tzinfo=UTC))
    make("Atrasada alta", due_date=date(2026, 5, 1), priority="high")
    make("Atrasada baixa", due_date=date(2026, 5, 1), priority="low")

    assert list_titles(overdue="true", priority="high") == ["Atrasada alta"]


@pytest.mark.parametrize(
    ("moment", "timezone", "overdue"),
    [
        # 23:59:59 of May 10 in São Paulo, already May 11 in UTC.
        (datetime(2026, 5, 11, 2, 59, 59, tzinfo=UTC), "America/Sao_Paulo", False),
        (datetime(2026, 5, 11, 2, 59, 59, tzinfo=UTC), "UTC", True),
        # Local midnight in São Paulo: May 11 begins and the task is now overdue.
        (datetime(2026, 5, 11, 3, 0, tzinfo=UTC), "America/Sao_Paulo", True),
    ],
    ids=["sp-before-midnight", "utc-same-instant", "sp-midnight"],
)
def test_overdue_uses_app_timezone(
    make, list_titles, freeze_now, override_settings, moment, timezone, overdue
):
    override_settings(app_timezone=timezone)
    freeze_now(moment)
    make("Vence dia 10", due_date=date(2026, 5, 10))

    assert list_titles(overdue="true") == (["Vence dia 10"] if overdue else [])


def test_search_in_title_and_description_ignoring_case(make, list_titles):
    make("Comprar LÂMPADA")
    make("Cozinha", description="trocar a lâmpada do teto")
    make("Outra coisa")

    assert sorted(list_titles(q="lâmpada")) == ["Comprar LÂMPADA", "Cozinha"]
    assert sorted(list_titles(q="  LÂMPADA  ")) == ["Comprar LÂMPADA", "Cozinha"]


@pytest.mark.parametrize(
    ("term", "expected"),
    [("100%", ["Desconto 100%"]), ("a_b", ["a_b"]), ("c\\d", ["c\\d"]), ("%", ["Desconto 100%"])],
    ids=["percent", "underscore", "backslash", "only-percent"],
)
def test_search_treats_like_wildcards_literally(make, list_titles, term, expected):
    make("Desconto 100%")
    make("Desconto 1000")
    make("a_b")
    make("axb")
    make("c\\d")
    make("cd")

    assert list_titles(q=term) == expected


def test_blank_search_is_ignored(make, list_titles):
    make("Uma")
    make("Outra")

    assert len(list_titles(q="   ")) == 2
    assert len(list_titles(q="")) == 2


# --- sorting -----------------------------------------------------------------------------------


@pytest.fixture
def sortable(make):
    make("Sem prazo baixa", priority="low")
    make("Dia 20 alta", priority="high", due_date=date(2026, 5, 20))
    make("Dia 10 média", priority="medium", due_date=date(2026, 5, 10))
    make("Sem prazo alta", priority="high")
    make("Dia 15 baixa", priority="low", due_date=date(2026, 5, 15))


@pytest.mark.usefixtures("sortable")
@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("due_date", ["Dia 10 média", "Dia 15 baixa", "Dia 20 alta"]),
        ("-due_date", ["Dia 20 alta", "Dia 15 baixa", "Dia 10 média"]),
        ("created_at", ["Sem prazo baixa", "Dia 20 alta", "Dia 10 média", "Sem prazo alta", "Dia 15 baixa"]),
        ("-created_at", ["Dia 15 baixa", "Sem prazo alta", "Dia 10 média", "Dia 20 alta", "Sem prazo baixa"]),
    ],
)
def test_sort_by_date_fields(list_titles, sort, expected):
    titles = list_titles(sort=sort)

    assert titles[: len(expected)] == expected
    if sort.endswith("due_date"):
        # Tasks without a due date always come last, in both directions.
        assert set(titles[len(expected) :]) == {"Sem prazo baixa", "Sem prazo alta"}


@pytest.mark.usefixtures("sortable")
def test_default_sort_is_newest_first(list_titles):
    assert list_titles() == list_titles(sort="-created_at")


@pytest.mark.usefixtures("sortable")
@pytest.mark.parametrize(
    ("sort", "expected"), [("priority", ["low", "medium", "high"]), ("-priority", ["high", "medium", "low"])]
)
def test_sort_by_priority_weight_not_alphabetically(client, ana, sort, expected):
    items = client.get(TASKS_URL, params={"sort": sort}, headers=ana[1]).json()["items"]

    priorities = [item["priority"] for item in items]
    assert list(dict.fromkeys(priorities)) == expected


def test_ties_are_broken_by_id(client, ana, create_task):
    same_moment = BASE
    tasks = [create_task(ana[0], f"T{i}", created_at=same_moment, priority="high") for i in range(5)]
    expected = sorted(str(task.id) for task in tasks)

    for sort in ("created_at", "-created_at", "priority", "-priority", "due_date", "-due_date"):
        items = client.get(TASKS_URL, params={"sort": sort}, headers=ana[1]).json()["items"]
        assert [item["id"] for item in items] == expected, sort


# --- pagination --------------------------------------------------------------------------------


def test_pagination_with_total(client, ana, make):
    for i in range(5):
        make(f"T{i}")

    response = client.get(TASKS_URL, params={"sort": "created_at", "limit": 2, "offset": 2}, headers=ana[1])

    body = response.json()
    assert [item["title"] for item in body["items"]] == ["T2", "T3"]
    assert (body["total"], body["limit"], body["offset"]) == (5, 2, 2)


def test_offset_past_the_end_returns_empty_page_with_total(client, ana, make):
    make("Única")

    body = client.get(TASKS_URL, params={"offset": 10}, headers=ana[1]).json()

    assert body["items"] == []
    assert body["total"] == 1


def test_total_counts_filtered_rows_not_the_page(client, ana, make):
    for i in range(3):
        make(f"Alta {i}", priority="high")
    make("Baixa", priority="low")

    body = client.get(TASKS_URL, params={"priority": "high", "limit": 1}, headers=ana[1]).json()

    assert len(body["items"]) == 1
    assert body["total"] == 3


def test_paging_through_ties_never_repeats_or_skips(client, ana, create_task):
    tasks = [create_task(ana[0], f"T{i}", created_at=BASE) for i in range(7)]

    seen = []
    for offset in range(0, 7, 3):
        params = {"sort": "-created_at", "limit": 3, "offset": offset}
        seen += [item["id"] for item in client.get(TASKS_URL, params=params, headers=ana[1]).json()["items"]]

    assert sorted(seen) == sorted(str(task.id) for task in tasks)
    assert len(seen) == len(set(seen))
