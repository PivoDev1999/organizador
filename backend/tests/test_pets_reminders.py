import uuid
from datetime import UTC, date, datetime, timedelta
from itertools import groupby

import pytest
from sqlalchemy import select

from app.core import clock
from app.core.pet_care import active_reminders, is_overdue, series_key
from app.models import PetEvent

PETS_URL = "/api/pets"
REMINDERS_URL = f"{PETS_URL}/reminders"
TODAY = date(2026, 10, 21)
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)  # 12:00 in America/Sao_Paulo
REMINDER_FIELDS = {
    "event_id",
    "pet_id",
    "pet_name",
    "type",
    "description",
    "occurred_on",
    "next_due_on",
    "overdue",
}


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: NOW)


@pytest.fixture
def ana(authenticate):
    return authenticate("ana@example.test")


@pytest.fixture
def headers(ana):
    return ana[1]


@pytest.fixture
def make_pet(client, headers):
    def _make(name: str, request_headers: dict | None = None) -> dict:
        response = client.post(
            PETS_URL, json={"name": name, "species": "Cachorro"}, headers=request_headers or headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def insert_event(db_session, ana):
    """Insert straight into the database: lets a test choose `created_at` (one transaction shares now())."""

    def _insert(
        pet: dict, type_: str, occurred: int, due: int | None, description=None, **fields
    ) -> PetEvent:
        event = PetEvent(
            user_id=fields.pop("user_id", ana[0].id),
            pet_id=uuid.UUID(pet["id"]),
            type=type_,
            occurred_on=day(occurred),
            next_due_on=day(due) if due is not None else None,
            description=description,
            **fields,
        )
        db_session.add(event)
        db_session.commit()
        return event

    return _insert


def reminders(client, headers, **params) -> list[dict]:
    response = client.get(REMINDERS_URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def summary(items: list[dict]) -> list[tuple[str, str | None, str]]:
    return [(item["pet_name"], item["description"], item["next_due_on"]) for item in items]


# --- window, order and overdue --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"within": 0}, ["Vermífugo", "Antipulgas", "Banho"]),
        ({}, ["Vermífugo", "Antipulgas", "Banho", "V10"]),
        ({"within": 365}, ["Vermífugo", "Antipulgas", "Banho", "V10", "V4"]),
    ],
)
def test_window_order_and_overdue(client, headers, make_pet, insert_event, params, expected):
    mel, frajola = make_pet("Mel"), make_pet("frajola")
    insert_event(mel, "medication", -40, -10, "Vermífugo")
    insert_event(mel, "grooming", -5, 0, "Banho")
    insert_event(frajola, "medication", -25, 0, "Antipulgas")
    insert_event(mel, "vaccine", -335, 30, "V10")
    insert_event(frajola, "vaccine", -200, 31, "V4")
    insert_event(mel, "vet", -3, None, "Check-up")

    items = reminders(client, headers, **params)

    assert [item["description"] for item in items] == expected
    assert all(set(item) == REMINDER_FIELDS for item in items)
    # Same due date: by pet name in pt-BR order, so "frajola" comes before "Mel" (byte order would not).
    assert [(item["pet_name"], item["overdue"]) for item in items[:3]] == [
        ("Mel", True),
        ("frajola", False),
        ("Mel", False),
    ]


def test_window_is_validated(client, headers):
    assert client.get(REMINDERS_URL, params={"within": 366}, headers=headers).status_code == 422


# --- series rule ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("newer", "resolved"),
    [
        ({"type": "vaccine", "description": "  v10 "}, True),
        ({"type": "vaccine", "description": "V10", "next_due_on": "2027-10-21"}, True),
        ({"type": "vaccine", "description": "Antirrábica"}, False),
        ({"type": "vet", "description": "V10"}, False),
        ({"type": "vaccine", "description": None}, False),
        # Inner whitespace is part of the description: only the ends are trimmed.
        ({"type": "vaccine", "description": "V\n10"}, False),
    ],
)
def test_newer_event_of_the_same_series_resolves_the_reminder(client, headers, make_pet, newer, resolved):
    mel = make_pet("Mel")
    events_url = f"{PETS_URL}/{mel['id']}/events"
    old = {"type": "vaccine", "occurred_on": "2025-10-21", "next_due_on": "2026-10-21", "description": "V10"}
    assert client.post(events_url, json=old, headers=headers).status_code == 201
    assert summary(reminders(client, headers)) == [("Mel", "V10", "2026-10-21")]

    response = client.post(events_url, json={"occurred_on": "2026-10-21", **newer}, headers=headers)
    assert response.status_code == 201

    old_listed = ("Mel", "V10", "2026-10-21") in summary(reminders(client, headers, within=365))
    assert old_listed is not resolved
    if "next_due_on" in newer:
        assert ("Mel", "V10", "2027-10-21") in summary(reminders(client, headers, within=365))


def test_null_description_series_and_other_pet(client, headers, make_pet, insert_event):
    mel, bidu = make_pet("Mel"), make_pet("Bidu")
    insert_event(mel, "medication", -60, 5)
    insert_event(bidu, "medication", -60, 6)
    insert_event(mel, "medication", -1, None)  # resolves Mel's NULL series only

    assert summary(reminders(client, headers)) == [("Bidu", None, day(6).isoformat())]


def test_same_occurred_on_is_resolved_by_created_at_then_id(client, headers, make_pet, insert_event):
    mel, bidu = make_pet("Mel"), make_pet("Bidu")
    base = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    insert_event(mel, "vaccine", 0, 10, "V10", created_at=base + timedelta(minutes=5))
    insert_event(mel, "vaccine", 0, 20, "v10", created_at=base)
    # Same occurred_on and created_at: the greater id wins.
    tied = [insert_event(bidu, "vaccine", 0, due, "V10", created_at=base) for due in (11, 12)]
    winner = max(tied, key=lambda event: event.id)

    assert summary(reminders(client, headers)) == [
        ("Mel", "V10", day(10).isoformat()),
        ("Bidu", "V10", winner.next_due_on.isoformat()),
    ]


def test_same_due_date_orders_by_pet_name_in_pt_br_then_id(client, headers, make_pet, insert_event):
    events = [insert_event(make_pet(name), "vet", -1, 5) for name in ("Zeca", "álvaro", "Bidu", "Bidu")]
    bidu_ids = sorted(str(event.id) for event in events[2:])

    listed = reminders(client, headers)

    # Byte order would give Bidu, Bidu, Zeca, álvaro.
    assert [item["pet_name"] for item in listed] == ["álvaro", "Bidu", "Bidu", "Zeca"]
    assert [item["event_id"] for item in listed[1:3]] == bidu_ids


def test_series_follows_edits_and_deletes_of_the_newer_event(client, headers, make_pet):
    mel = make_pet("Mel")
    events_url = f"{PETS_URL}/{mel['id']}/events"
    old = {"type": "vaccine", "occurred_on": "2025-10-21", "next_due_on": "2026-10-28", "description": "V10"}
    newer = {"type": "vaccine", "occurred_on": "2026-10-21", "description": "v10"}
    assert client.post(events_url, json=old, headers=headers).status_code == 201
    newer_url = f"{events_url}/{client.post(events_url, json=newer, headers=headers).json()['id']}"

    def old_is_listed() -> bool:
        return ("Mel", "V10", "2026-10-28") in summary(reminders(client, headers))

    def patch(body: dict) -> None:
        assert client.patch(newer_url, json=body, headers=headers).status_code == 200

    assert not old_is_listed()
    patch({"description": "Antirrábica"})
    assert old_is_listed()
    patch({"description": " V10 "})
    assert not old_is_listed()
    patch({"type": "vet"})
    assert old_is_listed()
    patch({"type": "vaccine"})
    assert not old_is_listed()
    assert client.delete(newer_url, headers=headers).status_code == 204
    assert old_is_listed()


def test_reminders_are_isolated_by_user(client, headers, authenticate, make_pet, insert_event):
    mel = make_pet("Mel")
    insert_event(mel, "vaccine", -10, 5, "V10")
    bia, bia_headers = authenticate("bia@example.test")
    rex = make_pet("Rex", bia_headers)
    insert_event(rex, "vaccine", -10, 6, "V10", user_id=bia.id)

    assert summary(reminders(client, headers)) == [("Mel", "V10", day(5).isoformat())]
    assert summary(reminders(client, bia_headers)) == [("Rex", "V10", day(6).isoformat())]


# --- SQL and pure rule agree ------------------------------------------------------------------------


def test_series_key_normalization():
    same = [(" İMUNO ", "i̇muno"), ("  V10 ", "v10"), (None, None)]
    different = [("Straße", "STRASSE"), (None, ""), ("V\n10", "V10"), ("V\t10", "V10"), ("\tV10", "V10")]

    assert all(series_key("vaccine", a) == series_key("vaccine", b) for a, b in same)
    assert all(series_key("vaccine", a) != series_key("vaccine", b) for a, b in different)
    assert series_key("vaccine", "V10") != series_key("vet", "V10")


def test_sql_agrees_with_the_pure_rule(client, headers, make_pet, insert_event, db_session):
    mel, bidu = make_pet("Mel"), make_pet("Bidu")
    base = datetime(2026, 10, 1, tzinfo=UTC)
    # Descriptions that tell normalizations apart: ICU lower case matches str.lower(), not casefold()
    # ("Straße" vs "STRASSE") nor the musl default collation ("İ" and the final sigma). Inner and
    # non-space whitespace is kept on both sides. `tie` rows share occurred_on and created_at.
    rows = [
        (mel, "vaccine", -300, 10, "Straße", None),
        (mel, "vaccine", -10, None, "STRASSE", None),
        (mel, "vaccine", -200, 3, "İMUNO", None),
        (mel, "vaccine", -5, None, "i̇muno", None),
        (mel, "other", -100, -2, "ΟΔΟΣ", None),
        (mel, "other", -50, None, "οδος", None),
        (mel, "other", -50, 40, "οδος", None),
        (mel, "medication", -20, 0, " Vermífugo", None),
        (mel, "medication", -20, 1, "vermífugo", None),
        (mel, "vet", -90, 4, "V10", None),
        (mel, "vet", -9, 6, "V\n10", None),
        (mel, "vet", -8, 7, "\tv10", None),
        (bidu, "vaccine", -300, 9, "Straße", None),
        (bidu, "grooming", -9, 25, None, None),
        (bidu, "grooming", -30, 2, None, None),
        (bidu, "vet", -1, 400, "Retorno", None),
        (bidu, "medication", -3, 4, "Antipulgas", "tie"),
        (bidu, "medication", -3, 8, "antipulgas", "tie"),
    ]
    for index, (pet, type_, occurred, due, description, tie) in enumerate(rows):
        created_at = base if tie else base + timedelta(minutes=index + 1)
        insert_event(pet, type_, occurred, due, description, created_at=created_at)
    stored = {str(event.id): event for event in db_session.scalars(select(PetEvent))}

    def by_due_date(ids: list[str]) -> list[tuple[date, set[str]]]:
        # The pure rule orders by due date only (same-day ties are broken by pet name in SQL).
        return [(due, set(group)) for due, group in groupby(ids, key=lambda id_: stored[id_].next_due_on)]

    for within in (0, 30, 365):
        expected = [str(event.id) for event in active_reminders(stored.values(), TODAY, within)]
        listed = reminders(client, headers, within=within)
        assert by_due_date([item["event_id"] for item in listed]) == by_due_date(expected)
        assert [item["overdue"] for item in listed] == [
            is_overdue(stored[item["event_id"]].next_due_on, TODAY) for item in listed
        ]
