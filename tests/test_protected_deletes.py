from decimal import Decimal

import pytest
from helpers import assert_error_schema

from tickets.models import Event, Reservation, ReservationSeat, Seat, Venue

pytestmark = pytest.mark.django_db


@pytest.fixture
def reservation(user, event, seats):
    created = Reservation.objects.create(user=user, event=event, total_price=Decimal("150.00"))
    ReservationSeat.objects.create(reservation=created, seat=seats[0], event=event)
    return created


def test_cannot_delete_venue_with_events(admin_client, venue, event):
    response = admin_client.delete(f"/api/venues/{venue.id}/")
    assert_error_schema(response, "conflict", 409)
    assert Venue.objects.filter(pk=venue.pk).exists()


def test_cannot_delete_event_with_reservations(admin_client, event, reservation):
    response = admin_client.delete(f"/api/events/{event.id}/")
    assert_error_schema(response, "conflict", 409)
    assert Event.objects.filter(pk=event.pk).exists()


def test_cannot_delete_reserved_seat(admin_client, seats, reservation):
    response = admin_client.delete(f"/api/seats/{seats[0].id}/")
    assert_error_schema(response, "conflict", 409)
    assert Seat.objects.filter(pk=seats[0].pk).exists()
