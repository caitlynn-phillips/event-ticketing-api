from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.utils import timezone
from helpers import assert_error_schema

from tickets.models import Event, Reservation, ReservationSeat, Seat, Venue

pytestmark = pytest.mark.django_db

URL = "/api/reservations/"


def book(client, event, seat_ids):
    return client.post(
        URL, {"event": event.id, "seat_ids": seat_ids}, format="json"
    )


@pytest.fixture
def unpublished_event(venue):
    start = timezone.now() + timedelta(days=20)
    return Event.objects.create(
        venue=venue,
        title="Hidden Show",
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        ticket_price=Decimal("10.00"),
        is_published=False,
    )


@pytest.fixture
def past_event(venue):
    start = timezone.now() - timedelta(days=1)
    return Event.objects.create(
        venue=venue,
        title="Old Show",
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        ticket_price=Decimal("10.00"),
    )


# ---------- creating reservations ----------

def test_booking_requires_authentication(api_client, event, seats):
    response = book(api_client, event, [seats[0].id])
    assert_error_schema(response, "authentication_failed", 401)


def test_user_can_book_seats(user_client, user, event, seats):
    response = book(user_client, event, [seats[0].id, seats[1].id])
    assert response.status_code == 201
    body = response.json()
    assert body["user"] == "alice"
    assert body["status"] == "confirmed"
    assert {s["id"] for s in body["seats"]} == {seats[0].id, seats[1].id}
    reservation = Reservation.objects.get(pk=body["id"])
    assert reservation.user == user
    assert reservation.reservation_seats.count() == 2


def test_total_price_calculated_server_side(user_client, event, seats):
    response = book(user_client, event, [seats[0].id, seats[1].id])
    assert response.json()["total_price"] == "300.00"


def test_client_cannot_set_status_or_price(user_client, event, seats):
    response = user_client.post(
        URL,
        {
            "event": event.id,
            "seat_ids": [seats[0].id],
            "status": "cancelled",
            "total_price": "1.00",
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["total_price"] == "150.00"


def test_double_booking_rejected(user_client, other_client, event, seats):
    assert book(user_client, event, [seats[0].id]).status_code == 201
    response = book(other_client, event, [seats[0].id])
    error = assert_error_schema(response, "validation_error", 400)
    assert "already reserved" in str(error["details"]["seat_ids"])


def test_failed_booking_is_all_or_nothing(user_client, other_client, event, seats):
    book(user_client, event, [seats[0].id])
    rejected = book(other_client, event, [seats[0].id, seats[1].id])
    assert rejected.status_code == 400
    # seat 2 must not have been held by the failed attempt
    retry = book(other_client, event, [seats[1].id])
    assert retry.status_code == 201


def test_duplicate_seats_in_request_rejected(user_client, event, seats):
    response = book(user_client, event, [seats[0].id, seats[0].id])
    error = assert_error_schema(response, "validation_error", 400)
    assert "seat_ids" in error["details"]


def test_seat_from_other_venue_rejected(user_client, event):
    other = Venue.objects.create(name="Other", address="3 St", city="Paarl")
    foreign = Seat.objects.create(venue=other, section="Z", row="1", number=1)
    response = book(user_client, event, [foreign.id])
    error = assert_error_schema(response, "validation_error", 400)
    assert "seat_ids" in error["details"]


def test_empty_seat_list_rejected(user_client, event):
    response = book(user_client, event, [])
    error = assert_error_schema(response, "validation_error", 400)
    assert "seat_ids" in error["details"]


def test_unknown_seat_rejected(user_client, event):
    response = book(user_client, event, [99999])
    error = assert_error_schema(response, "validation_error", 400)
    assert "seat_ids" in error["details"]


def test_missing_event_rejected(user_client, seats):
    response = user_client.post(URL, {"seat_ids": [seats[0].id]}, format="json")
    error = assert_error_schema(response, "validation_error", 400)
    assert "event" in error["details"]


def test_unpublished_event_rejected(user_client, unpublished_event, seats):
    response = book(user_client, unpublished_event, [seats[0].id])
    error = assert_error_schema(response, "validation_error", 400)
    assert "event" in error["details"]


def test_past_event_rejected(user_client, past_event, seats):
    response = book(user_client, past_event, [seats[0].id])
    error = assert_error_schema(response, "validation_error", 400)
    assert "event" in error["details"]


def test_concurrent_insert_conflict_returns_400(user_client, event, seats):
    """If the DB constraint trips after validation passed, return a clean 400."""
    with patch.object(
        ReservationSeat.objects, "bulk_create", side_effect=IntegrityError
    ):
        response = book(user_client, event, [seats[0].id])
    error = assert_error_schema(response, "validation_error", 400)
    assert "seat_ids" in error["details"]
    assert Reservation.objects.count() == 0


# ---------- listing and retrieving ----------

def test_user_lists_only_own_reservations(user_client, other_client, event, seats):
    book(user_client, event, [seats[0].id])
    book(other_client, event, [seats[1].id])
    response = user_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["user"] == "alice"


def test_admin_lists_all_reservations(admin_client, user_client, other_client, event, seats):
    book(user_client, event, [seats[0].id])
    book(other_client, event, [seats[1].id])
    response = admin_client.get(URL)
    assert response.json()["count"] == 2


def test_user_can_retrieve_own_reservation(user_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = user_client.get(f"{URL}{created['id']}/")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_user_cannot_retrieve_others_reservation(user_client, other_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = other_client.get(f"{URL}{created['id']}/")
    assert_error_schema(response, "not_found", 404)


def test_reservation_cannot_be_updated(user_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = user_client.put(
        f"{URL}{created['id']}/",
        {"event": event.id, "seat_ids": [seats[1].id]},
        format="json",
    )
    assert_error_schema(response, "method_not_allowed", 405)


# ---------- cancelling ----------

def test_cancel_own_reservation(user_client, event, seats):
    created = book(user_client, event, [seats[0].id, seats[1].id]).json()
    response = user_client.post(f"{URL}{created['id']}/cancel/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["seats"] == []
    assert ReservationSeat.objects.count() == 0


def test_cancel_frees_seats_for_rebooking(user_client, other_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    user_client.post(f"{URL}{created['id']}/cancel/")
    response = book(other_client, event, [seats[0].id])
    assert response.status_code == 201


def test_cancel_twice_rejected(user_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    user_client.post(f"{URL}{created['id']}/cancel/")
    response = user_client.post(f"{URL}{created['id']}/cancel/")
    error = assert_error_schema(response, "validation_error", 400)
    assert "already cancelled" in str(error["details"])


def test_user_cannot_cancel_others_reservation(user_client, other_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = other_client.post(f"{URL}{created['id']}/cancel/")
    assert_error_schema(response, "not_found", 404)
    assert Reservation.objects.get(pk=created["id"]).status == "confirmed"


def test_admin_can_cancel_any_reservation(admin_client, user_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = admin_client.post(f"{URL}{created['id']}/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_requires_authentication(api_client, user_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = api_client.post(f"{URL}{created['id']}/cancel/")
    assert_error_schema(response, "authentication_failed", 401)


# ---------- deleting ----------

def test_user_can_delete_own_reservation_and_free_seats(
    user_client, other_client, event, seats
):
    created = book(user_client, event, [seats[0].id]).json()
    response = user_client.delete(f"{URL}{created['id']}/")
    assert response.status_code == 204
    assert not Reservation.objects.filter(pk=created["id"]).exists()
    assert book(other_client, event, [seats[0].id]).status_code == 201


def test_user_cannot_delete_others_reservation(user_client, other_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = other_client.delete(f"{URL}{created['id']}/")
    assert_error_schema(response, "not_found", 404)
    assert Reservation.objects.filter(pk=created["id"]).exists()


def test_admin_can_delete_any_reservation(admin_client, user_client, event, seats):
    created = book(user_client, event, [seats[0].id]).json()
    response = admin_client.delete(f"{URL}{created['id']}/")
    assert response.status_code == 204
