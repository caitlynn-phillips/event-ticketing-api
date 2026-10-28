from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from tickets.models import Event, Reservation, ReservationSeat, Seat, Venue

pytestmark = pytest.mark.django_db


def test_venue_str(venue):
    assert str(venue) == "Test Arena"


def test_event_str(event):
    assert "Summer Concert" in str(event)


def test_event_end_before_start_invalid(venue):
    now = timezone.now()
    event = Event(
        venue=venue,
        title="Bad Event",
        starts_at=now,
        ends_at=now - timedelta(hours=1),
        ticket_price=Decimal("10.00"),
    )
    with pytest.raises(ValidationError):
        event.clean()


def test_event_valid_dates_pass_clean(event):
    event.clean()


def test_seat_str(seats):
    assert str(seats[0]) == "A-B1 @ Test Arena"


def test_duplicate_seat_in_venue_rejected(venue, seats):
    with pytest.raises(IntegrityError), transaction.atomic():
        Seat.objects.create(venue=venue, section="A", row="B", number=1)


def test_reservation_seat_copies_event_from_reservation(user, event, seats):
    reservation = Reservation.objects.create(
        user=user, event=event, total_price=Decimal("150.00")
    )
    link = ReservationSeat(reservation=reservation, seat=seats[0])
    link.save()
    assert link.event_id == event.id


def test_same_seat_cannot_be_held_twice_for_one_event(
    user, other_user, event, seats
):
    first = Reservation.objects.create(
        user=user, event=event, total_price=Decimal("150.00")
    )
    second = Reservation.objects.create(
        user=other_user, event=event, total_price=Decimal("150.00")
    )
    ReservationSeat.objects.create(reservation=first, seat=seats[0], event=event)
    with pytest.raises(IntegrityError), transaction.atomic():
        ReservationSeat.objects.create(
            reservation=second, seat=seats[0], event=event
        )


def test_seat_from_other_venue_rejected(user, event):
    other_venue = Venue.objects.create(name="Other", address="2 Side St", city="Cape Town")
    foreign_seat = Seat.objects.create(
        venue=other_venue, section="Z", row="1", number=1
    )
    reservation = Reservation.objects.create(
        user=user, event=event, total_price=Decimal("150.00")
    )
    with pytest.raises(ValidationError):
        ReservationSeat(reservation=reservation, seat=foreign_seat).save()
