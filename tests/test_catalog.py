from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from helpers import assert_error_schema

from tickets.models import Event, Seat, Venue

pytestmark = pytest.mark.django_db

VENUES = "/api/venues/"
SEATS = "/api/seats/"
EVENTS = "/api/events/"


def event_payload(venue, **overrides):
    start = timezone.now() + timedelta(days=10)
    payload = {
        "venue": venue.id,
        "title": "New Show",
        "description": "",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=3)).isoformat(),
        "ticket_price": "99.50",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def hidden_event(venue):
    start = timezone.now() + timedelta(days=20)
    return Event.objects.create(
        venue=venue,
        title="Hidden Show",
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        ticket_price=Decimal("10.00"),
        is_published=False,
    )


# ---------- venues ----------

def test_venues_require_authentication(api_client):
    response = api_client.get(VENUES)
    assert_error_schema(response, "authentication_failed", 401)


def test_user_can_list_and_retrieve_venues(user_client, venue):
    listing = user_client.get(VENUES)
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    detail = user_client.get(f"{VENUES}{venue.id}/")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Test Arena"


def test_user_cannot_create_venue(user_client):
    response = user_client.post(
        VENUES,
        {"name": "Nope", "address": "1 St", "city": "Durban"},
        format="json",
    )
    assert_error_schema(response, "permission_denied", 403)
    assert Venue.objects.count() == 0


def test_admin_can_create_venue(admin_client):
    response = admin_client.post(
        VENUES,
        {"name": "New Hall", "address": "2 Road", "city": "Cape Town"},
        format="json",
    )
    assert response.status_code == 201
    assert Venue.objects.filter(name="New Hall").exists()


def test_venue_missing_name_rejected(admin_client):
    response = admin_client.post(
        VENUES, {"address": "2 Road", "city": "Cape Town"}, format="json"
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "name" in error["details"]


def test_venue_duplicate_name_rejected(admin_client, venue):
    response = admin_client.post(
        VENUES,
        {"name": "Test Arena", "address": "9 Road", "city": "Durban"},
        format="json",
    )
    assert_error_schema(response, "validation_error", 400)


def test_admin_can_update_venue(admin_client, venue):
    response = admin_client.patch(
        f"{VENUES}{venue.id}/", {"city": "Pretoria"}, format="json"
    )
    assert response.status_code == 200
    venue.refresh_from_db()
    assert venue.city == "Pretoria"


def test_user_cannot_update_or_delete_venue(user_client, venue):
    patch = user_client.patch(
        f"{VENUES}{venue.id}/", {"city": "Pretoria"}, format="json"
    )
    assert_error_schema(patch, "permission_denied", 403)
    delete = user_client.delete(f"{VENUES}{venue.id}/")
    assert_error_schema(delete, "permission_denied", 403)
    assert Venue.objects.filter(pk=venue.pk).exists()


def test_admin_can_delete_venue_without_events(admin_client, venue):
    response = admin_client.delete(f"{VENUES}{venue.id}/")
    assert response.status_code == 204
    assert not Venue.objects.filter(pk=venue.pk).exists()


# ---------- seats ----------

def test_user_can_list_seats_filtered_by_venue(user_client, venue, seats):
    other = Venue.objects.create(name="Other", address="3 St", city="Paarl")
    Seat.objects.create(venue=other, section="Z", row="1", number=1)
    response = user_client.get(f"{SEATS}?venue={venue.id}")
    assert response.status_code == 200
    assert response.json()["count"] == 3


def test_user_cannot_create_seat(user_client, venue):
    response = user_client.post(
        SEATS,
        {"venue": venue.id, "section": "C", "row": "1", "number": 1},
        format="json",
    )
    assert_error_schema(response, "permission_denied", 403)


def test_admin_can_create_seat(admin_client, venue):
    response = admin_client.post(
        SEATS,
        {"venue": venue.id, "section": "C", "row": "1", "number": 5},
        format="json",
    )
    assert response.status_code == 201
    assert Seat.objects.filter(venue=venue, section="C", number=5).exists()


def test_duplicate_seat_rejected(admin_client, venue, seats):
    response = admin_client.post(
        SEATS,
        {"venue": venue.id, "section": "A", "row": "B", "number": 1},
        format="json",
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "non_field_errors" in error["details"]


def test_seat_number_zero_rejected(admin_client, venue):
    response = admin_client.post(
        SEATS,
        {"venue": venue.id, "section": "C", "row": "1", "number": 0},
        format="json",
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "number" in error["details"]


def test_admin_can_delete_unreserved_seat(admin_client, seats):
    response = admin_client.delete(f"{SEATS}{seats[0].id}/")
    assert response.status_code == 204


# ---------- events ----------

def test_user_sees_only_published_events(user_client, event, hidden_event):
    response = user_client.get(EVENTS)
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["title"] == "Summer Concert"


def test_admin_sees_unpublished_events(admin_client, event, hidden_event):
    response = admin_client.get(EVENTS)
    assert response.json()["count"] == 2


def test_user_cannot_retrieve_unpublished_event(user_client, hidden_event):
    response = user_client.get(f"{EVENTS}{hidden_event.id}/")
    assert_error_schema(response, "not_found", 404)


def test_user_cannot_create_event(user_client, venue):
    response = user_client.post(EVENTS, event_payload(venue), format="json")
    assert_error_schema(response, "permission_denied", 403)


def test_admin_can_create_event(admin_client, venue):
    response = admin_client.post(EVENTS, event_payload(venue), format="json")
    assert response.status_code == 201
    assert response.json()["ticket_price"] == "99.50"
    assert Event.objects.filter(title="New Show").exists()


def test_event_end_before_start_rejected(admin_client, venue):
    now = timezone.now() + timedelta(days=10)
    payload = event_payload(
        venue,
        starts_at=now.isoformat(),
        ends_at=(now - timedelta(hours=1)).isoformat(),
    )
    response = admin_client.post(EVENTS, payload, format="json")
    error = assert_error_schema(response, "validation_error", 400)
    assert "ends_at" in error["details"]


def test_event_negative_price_rejected(admin_client, venue):
    response = admin_client.post(
        EVENTS, event_payload(venue, ticket_price="-5.00"), format="json"
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "ticket_price" in error["details"]


def test_event_unknown_venue_rejected(admin_client, venue):
    response = admin_client.post(
        EVENTS, {**event_payload(venue), "venue": 99999}, format="json"
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "venue" in error["details"]


def test_patch_cannot_move_end_before_existing_start(admin_client, event):
    early = (event.starts_at - timedelta(hours=1)).isoformat()
    response = admin_client.patch(
        f"{EVENTS}{event.id}/", {"ends_at": early}, format="json"
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "ends_at" in error["details"]


def test_admin_can_unpublish_event(admin_client, user_client, event):
    response = admin_client.patch(
        f"{EVENTS}{event.id}/", {"is_published": False}, format="json"
    )
    assert response.status_code == 200
    assert user_client.get(EVENTS).json()["count"] == 0


def test_events_filtered_by_venue(user_client, venue, event):
    other = Venue.objects.create(name="Other", address="3 St", city="Paarl")
    start = timezone.now() + timedelta(days=5)
    Event.objects.create(
        venue=other,
        title="Elsewhere",
        starts_at=start,
        ends_at=start + timedelta(hours=1),
        ticket_price=Decimal("5.00"),
    )
    response = user_client.get(f"{EVENTS}?venue={venue.id}")
    assert response.json()["count"] == 1


def test_admin_can_delete_event_without_reservations(admin_client, event):
    response = admin_client.delete(f"{EVENTS}{event.id}/")
    assert response.status_code == 204
