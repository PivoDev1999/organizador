"""GET /api/tasks: filter combinations, isolation, search, sorting and paging edge cases."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import clock
from app.repositories.task import PRIORITY_WEIGHT

TASKS_URL = "/api/tasks"
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
# 12:00 in São Paulo on 2026-05-10: "today" for the overdue filter.
NOW = datetime(2026, 5, 10, 15, 0, tzinfo=UTC)
WEIGHT = {p.value: w for p, w in PRIORITY_WEIGHT.items()}


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def bia(authenticate):
    return authenticate("bia@example.test")


@pytest.fixture
def freeze_now(monkeypatch):
    def _freeze(moment: datetime) -> None:
        monkeypatch.setattr(clock, "now_utc", lambda: moment)

    return _freeze


@pytest.fixture
def get_page(client, ana):
    def _get(headers=None, **params) -> dict:
        response = client.get(TASKS_URL, params=params, headers=headers or ana[1])
        assert response.status_code == 200, response.text
        return response.json()

    return _get


@pytest.fixture
def make(create_task):
    """Create a task for `user` with increasing created_at (deterministic creation order)."""
    counter = iter(range(10_000))

    def _make(user, title: str, **fields):
        fields.setdefault("created_at", BASE + timedelta(minutes=next(counter)))
        return create_task(user, title, **fields)

    return _make


def titles(page: dict) -> list[str]:
    return [item["title"] for item in page["items"]]


# --- combined filters --------------------------------------------------------------------------


FILTER_DATASET = [
    # title, status, priority, due_date
    ("Conta de luz A", "doing", "high", date(2026, 5, 5)),  # matches every filter below
    ("Conta de luz B", "todo", "high", date(2026, 5, 5)),
    ("Conta de luz C", "doing", "low", date(2026, 5, 5)),
    ("Aluguel D", "doing", "high", date(2026, 5, 5)),
    ("Conta de luz E", "doing", "high", date(2026, 5, 12)),  # in range, not overdue
    ("Conta de luz F", "doing", "high", date(2026, 4, 30)),  # overdue, before the range
    ("Conta de luz G", "doing", "high", None),
    ("Conta de luz H", "done", "high", date(2026, 5, 5)),
]
RANGE = {"due_from": "2026-05-01", "due_to": "2026-05-20"}


@pytest.fixture
def filter_dataset(ana, bia, make, freeze_now, override_settings):
    override_settings(app_timezone="America/Sao_Paulo")
    freeze_now(NOW)
    for user in (ana[0], bia[0]):  # Bia has an identical copy of every task
        for title, status, priority, due in FILTER_DATASET:
            make(user, title, status=status, priority=priority, due_date=due)


COMBINATIONS = [
    ({"status": "doing", "priority": "high", "q": "luz", "overdue": "true", **RANGE}, ["A"]),
    ({"status": "doing", "priority": "high", "q": "luz"}, ["A", "E", "F", "G"]),
    ({"overdue": "true", "q": "luz"}, ["A", "B", "C", "F"]),
    ({"priority": "high", **RANGE}, ["A", "B", "D", "E", "H"]),
    ({"status": ["doing", "done"], "overdue": "true"}, ["A", "C", "D", "F"]),
    ({"q": "LUZ", "due_to": "2026-05-05"}, ["A", "B", "C", "F", "H"]),
    ({"status": "done", "overdue": "true"}, []),
    ({"overdue": "true", **RANGE}, ["A", "B", "C", "D"]),
    ({"priority": ["low", "medium"], "q": "aluguel"}, []),
    ({"due_from": "2026-05-05", "due_to": "2026-05-05", "status": "todo"}, ["B"]),
]


@pytest.mark.usefixtures("filter_dataset")
@pytest.mark.parametrize(("params", "expected"), COMBINATIONS)
def test_filters_combine_with_and(get_page, params, expected):
    page = get_page(**params, limit=100)

    assert sorted(title[-1] for title in titles(page)) == expected
    assert page["total"] == len(expected)


@pytest.mark.usefixtures("filter_dataset")
@pytest.mark.parametrize(("params", "expected"), COMBINATIONS)
def test_list_never_includes_other_users_tasks(get_page, ana, bia, params, expected):
    ana_page = get_page(**params, limit=100)
    bia_page = get_page(headers=bia[1], **params, limit=100)

    ana_ids = {item["id"] for item in ana_page["items"]}
    bia_ids = {item["id"] for item in bia_page["items"]}
    # Same data, same filters: same titles, but never the same rows.
    assert sorted(titles(ana_page)) == sorted(titles(bia_page))
    assert ana_ids.isdisjoint(bia_ids)
    assert ana_page["total"] == bia_page["total"] == len(expected)


@pytest.mark.usefixtures("filter_dataset")
def test_total_only_counts_own_tasks(get_page):
    page = get_page(limit=1)

    assert page["total"] == len(FILTER_DATASET)


@pytest.mark.usefixtures("filter_dataset")
def test_unknown_query_params_are_ignored_and_cannot_switch_owner(get_page, bia):
    page = get_page(user_id=str(bia[0].id), owner="bia", limit=100)

    assert page["total"] == len(FILTER_DATASET)


def test_user_without_tasks_sees_empty_list_while_others_have_tasks(get_page, ana, bia, make):
    for i in range(3):
        make(bia[0], f"Bia {i}")

    assert get_page() == {"items": [], "total": 0, "limit": 20, "offset": 0}


# --- overdue -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("due", "status", "overdue"),
    [
        (date(2026, 5, 10), "todo", False),
        (date(2026, 5, 9), "todo", True),
        (date(2026, 5, 9), "doing", True),
        (date(2026, 5, 9), "done", False),
        (None, "todo", False),
        (date(2026, 5, 11), "todo", False),
        (date(2000, 1, 1), "todo", True),
    ],
    ids=["today", "yesterday", "yesterday-doing", "yesterday-done", "no-due-date", "tomorrow", "long-ago"],
)
def test_overdue_single_task(ana, make, get_page, freeze_now, override_settings, due, status, overdue):
    override_settings(app_timezone="America/Sao_Paulo")
    freeze_now(NOW)
    make(ana[0], "T", due_date=due, status=status)

    assert titles(get_page(overdue="true")) == (["T"] if overdue else [])


@pytest.mark.parametrize(
    ("moment", "timezone", "overdue"),
    [
        # 23:59 of May 10 in São Paulo (02:59 UTC on May 11): the task due May 10 is not late yet.
        (datetime(2026, 5, 11, 2, 59, tzinfo=UTC), "America/Sao_Paulo", False),
        (datetime(2026, 5, 11, 2, 59, tzinfo=UTC), "UTC", True),
        (datetime(2026, 5, 11, 3, 0, tzinfo=UTC), "America/Sao_Paulo", True),
        # Tokyo (UTC+9) already lives on May 11 at 15:00 UTC of May 10.
        (datetime(2026, 5, 10, 15, 0, tzinfo=UTC), "Asia/Tokyo", True),
        (datetime(2026, 5, 10, 14, 59, tzinfo=UTC), "Asia/Tokyo", False),
        # Pago Pago (UTC-11) is still on May 10 at 10:59 UTC of May 11.
        (datetime(2026, 5, 11, 10, 59, tzinfo=UTC), "Pacific/Pago_Pago", False),
        (datetime(2026, 5, 11, 11, 0, tzinfo=UTC), "Pacific/Pago_Pago", True),
    ],
    ids=[
        "sp-23h59",
        "utc-same-instant",
        "sp-midnight",
        "tokyo-midnight",
        "tokyo-23h59",
        "pago-23h59",
        "pago-0h",
    ],
)
def test_overdue_day_boundary_in_app_timezone(
    ana, make, get_page, freeze_now, override_settings, moment, timezone, overdue
):
    override_settings(app_timezone=timezone)
    freeze_now(moment)
    make(ana[0], "Vence dia 10", due_date=date(2026, 5, 10))

    assert titles(get_page(overdue="true")) == (["Vence dia 10"] if overdue else [])


@pytest.mark.parametrize("value", ["true", "1", "yes", "on"])
def test_overdue_accepts_boolean_spellings(ana, make, get_page, freeze_now, value):
    freeze_now(NOW)
    make(ana[0], "Atrasada", due_date=date(2026, 1, 1))
    make(ana[0], "Futura", due_date=date(2027, 1, 1))

    assert titles(get_page(overdue=value)) == ["Atrasada"]


# --- due range ---------------------------------------------------------------------------------


@pytest.fixture
def dated(ana, make):
    for day in (9, 10, 11):
        make(ana[0], f"Dia {day}", due_date=date(2026, 5, day))
    make(ana[0], "Sem prazo")


@pytest.mark.usefixtures("dated")
@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"due_from": "2026-05-10", "due_to": "2026-05-10"}, ["Dia 10"]),
        ({"due_from": "2026-05-09", "due_to": "2026-05-11"}, ["Dia 10", "Dia 11", "Dia 9"]),
        ({"due_from": "2026-05-11"}, ["Dia 11"]),
        ({"due_to": "2026-05-09"}, ["Dia 9"]),
        ({"due_from": "2026-05-12"}, []),
        ({"due_from": "2000-01-01"}, ["Dia 10", "Dia 11", "Dia 9"]),
    ],
    ids=["single-day", "both-limits", "from-last-day", "to-first-day", "after-all", "open-ended"],
)
def test_due_range_limits_are_inclusive_and_exclude_null(get_page, params, expected):
    assert sorted(titles(get_page(**params))) == expected


@pytest.mark.parametrize(
    "value", ["2026-05-10T00:00:00", "1778371200", "0"], ids=["midnight", "unix", "zero"]
)
def test_due_range_rejects_non_date_values(client, ana, value):
    response = client.get(TASKS_URL, params={"due_from": value}, headers=ana[1])

    assert response.status_code == 422


# --- search ------------------------------------------------------------------------------------


def test_search_does_not_ignore_accents(ana, make, get_page):
    """Documents current behavior: ILIKE folds case but not accents ("lampada" misses "lâmpada")."""
    make(ana[0], "Trocar lâmpada")
    make(ana[0], "Trocar lampada")

    assert titles(get_page(q="lampada")) == ["Trocar lampada"]
    assert titles(get_page(q="lâmpada")) == ["Trocar lâmpada"]
    assert sorted(titles(get_page(q="LAMPADA"))) == ["Trocar lampada"]


def test_search_folds_case_of_non_ascii_letters(ana, make, get_page):
    make(ana[0], "AÇÃO URGENTE")

    assert titles(get_page(q="ação")) == ["AÇÃO URGENTE"]


def test_search_matches_description_only_and_ignores_null_description(ana, make, get_page):
    make(ana[0], "Cozinha", description="comprar detergente")
    make(ana[0], "Detergente acabou")
    make(ana[0], "Sem descrição")

    assert sorted(titles(get_page(q="detergente"))) == ["Cozinha", "Detergente acabou"]
    assert titles(get_page(q="descrição")) == ["Sem descrição"]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("50%_off", ["50%_off"]),
        ("\\%", ["a\\%b"]),
        ("\\\\", ["c\\\\d"]),
        ("_", ["50%_off", "500_of"]),
        ("%%", []),
    ],
    ids=["percent-underscore", "backslash-percent", "double-backslash", "only-underscore", "double-percent"],
)
def test_search_wildcards_and_escape_combinations_are_literal(ana, make, get_page, term, expected):
    for title in ("50%_off", "50%xoff", "500_of", "a\\%b", "a%b", "c\\\\d", "c\\d"):
        make(ana[0], title)

    assert sorted(titles(get_page(q=term))) == sorted(expected)


def test_search_with_emoji(ana, make, get_page):
    make(ana[0], "Festa 🎉")
    make(ana[0], "Festa")

    assert titles(get_page(q="🎉")) == ["Festa 🎉"]


@pytest.mark.parametrize("term", ["a" * 200, f"  {'a' * 200}  "], ids=["exact-200", "200-with-padding"])
def test_search_with_200_characters_is_accepted(client, ana, term):
    response = client.get(TASKS_URL, params={"q": term}, headers=ana[1])

    assert response.status_code == 200


def test_search_with_201_characters_is_rejected(client, ana):
    response = client.get(TASKS_URL, params={"q": "a" * 201}, headers=ana[1])

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "A busca deve ter no máximo 200 caracteres."


@pytest.mark.parametrize("term", ["   ", "\t", ""], ids=["spaces", "tab", "empty"])
def test_blank_search_equals_no_search(ana, make, get_page, term):
    make(ana[0], "Uma")
    make(ana[0], "Outra", description="desc")

    assert get_page(q=term) == get_page()


# --- repeated params ---------------------------------------------------------------------------


def test_repeated_status_and_priority_do_not_duplicate_rows(ana, make, get_page):
    make(ana[0], "A", status="todo", priority="high")
    make(ana[0], "B", status="doing", priority="high")

    page = get_page(status=["todo", "todo"], priority=["high", "high", "high"])

    assert titles(page) == ["A"]
    assert page["total"] == 1


def test_repeated_scalar_param_uses_last_value(ana, make, get_page):
    for i in range(3):
        make(ana[0], f"T{i}")

    page = get_page(limit=[1, 2])

    assert page["limit"] == 2
    assert len(page["items"]) == 2


# --- sorting -----------------------------------------------------------------------------------


@pytest.fixture
def tied(ana, create_task):
    """Tasks with many ties on every sortable column, including several without due date."""
    rows = [
        ("high", date(2026, 5, 10)),
        ("high", date(2026, 5, 10)),
        ("low", date(2026, 5, 10)),
        ("medium", None),
        ("high", None),
        ("low", None),
        ("medium", date(2026, 5, 1)),
        ("low", date(2026, 5, 20)),
        ("medium", date(2026, 5, 1)),
    ]
    created = [BASE, BASE, BASE + timedelta(hours=1)]
    return [
        create_task(ana[0], f"T{i}", priority=p, due_date=d, created_at=created[i % 3])
        for i, (p, d) in enumerate(rows)
    ]


def _expected_order(tasks, sort: str) -> list[str]:
    """Order the API must return: primary key per `sort` (NULLS LAST for due_date), then id ascending."""
    desc = sort.startswith("-")
    field = sort.lstrip("-")
    sign = -1 if desc else 1

    def key(task):
        if field == "due_date":
            rank = (1, 0) if task.due_date is None else (0, sign * task.due_date.toordinal())
        elif field == "priority":
            rank = sign * WEIGHT[task.priority]
        else:
            rank = sign * task.created_at.timestamp()
        return (rank, str(task.id))  # uuid order in Postgres == order of the lowercase hex string

    return [str(task.id) for task in sorted(tasks, key=key)]


@pytest.mark.parametrize(
    "sort", ["due_date", "-due_date", "priority", "-priority", "created_at", "-created_at"]
)
def test_sort_with_ties_is_total_and_broken_by_id(get_page, tied, sort):
    page = get_page(sort=sort, limit=100)

    assert [item["id"] for item in page["items"]] == _expected_order(tied, sort)


@pytest.mark.parametrize("sort", ["due_date", "-due_date"])
def test_tasks_without_due_date_are_last_in_both_directions(get_page, tied, sort):
    items = get_page(sort=sort, limit=100)["items"]

    dues = [item["due_date"] for item in items]
    first_null = dues.index(None)
    assert all(due is None for due in dues[first_null:])
    assert all(due is not None for due in dues[:first_null])
    # Among themselves, the undated tasks follow the id tie-breaker (ascending even for -due_date).
    null_ids = [item["id"] for item in items[first_null:]]
    assert null_ids == sorted(null_ids)


def test_desc_priority_breaks_ties_by_ascending_id(get_page, tied):
    items = get_page(sort="-priority", limit=100)["items"]

    for priority in ("high", "medium", "low"):
        ids = [item["id"] for item in items if item["priority"] == priority]
        assert ids == sorted(ids), priority
    assert [item["priority"] for item in items] == sorted(
        (item["priority"] for item in items), key=lambda p: -WEIGHT[p]
    )


@pytest.mark.parametrize(
    "sort",
    ["+due_date", "DUE_DATE", "--priority", "", "due_date,priority", "-id", "title", " due_date"],
    ids=["plus-prefix", "upper", "double-minus", "empty", "comma-list", "id", "title", "leading-space"],
)
def test_invalid_sort_is_rejected(client, ana, sort):
    response = client.get(TASKS_URL, params={"sort": sort}, headers=ana[1])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "sort"]


# --- pagination --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"limit": -1},
        {"limit": 0},
        {"limit": 101},
        {"limit": "dez"},
        {"limit": 1.5},
        {"offset": -1},
        {"offset": 2**31},
        {"offset": "x"},
    ],
    ids=["limit-negative", "limit-zero", "limit-101", "limit-text", "limit-float", "offset-negative",
         "offset-too-big", "offset-text"],
)  # fmt: skip
def test_invalid_paging_is_rejected(client, ana, params):
    response = client.get(TASKS_URL, params=params, headers=ana[1])

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", next(iter(params))]


@pytest.mark.parametrize("limit", [1, 100])
def test_limit_bounds_are_accepted(ana, make, get_page, limit):
    for i in range(3):
        make(ana[0], f"T{i}")

    page = get_page(limit=limit)

    assert len(page["items"]) == min(limit, 3)
    assert (page["total"], page["limit"]) == (3, limit)


def test_default_limit_is_20(ana, make, get_page):
    for i in range(25):
        make(ana[0], f"T{i}")

    page = get_page()

    assert len(page["items"]) == 20
    assert page["total"] == 25


@pytest.mark.parametrize("offset", [3, 4, 2**31 - 1], ids=["equal-total", "past-total", "max-offset"])
def test_offset_at_or_past_the_end_returns_empty_items_with_total(ana, make, get_page, offset):
    for i in range(3):
        make(ana[0], f"T{i}")

    page = get_page(offset=offset)

    assert page == {"items": [], "total": 3, "limit": 20, "offset": offset}


@pytest.mark.parametrize(
    "sort", ["due_date", "-due_date", "priority", "-priority", "created_at", "-created_at"]
)
@pytest.mark.parametrize("limit", [1, 2, 4, 9, 10])
def test_walking_all_pages_returns_every_task_once_in_order(get_page, tied, sort, limit):
    full = [item["id"] for item in get_page(sort=sort, limit=100)["items"]]

    walked = []
    offset = 0
    while True:
        page = get_page(sort=sort, limit=limit, offset=offset)
        assert page["total"] == len(tied)
        if not page["items"]:
            break
        walked += [item["id"] for item in page["items"]]
        offset += limit

    assert walked == full
    assert len(set(walked)) == len(tied)


def test_paging_with_filters_keeps_filtered_total(ana, make, get_page):
    for i in range(5):
        make(ana[0], f"Alta {i}", priority="high")
        make(ana[0], f"Baixa {i}", priority="low")

    pages = [get_page(priority="high", sort="created_at", limit=2, offset=o) for o in (0, 2, 4)]

    assert [p["total"] for p in pages] == [5, 5, 5]
    assert sum((titles(p) for p in pages), []) == [f"Alta {i}" for i in range(5)]
