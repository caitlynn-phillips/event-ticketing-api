from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Venue(models.Model):
    name = models.CharField(max_length=200, unique=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Event(models.Model):
    venue = models.ForeignKey(
        Venue, on_delete=models.PROTECT, related_name="events"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    ticket_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["venue", "starts_at"], name="event_venue_start_idx"),
            models.Index(fields=["is_published", "starts_at"], name="event_pub_start_idx"),
        ]

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "ends_at must be after starts_at."})

    def __str__(self):
        return f"{self.title} ({self.starts_at:%Y-%m-%d})"


class Seat(models.Model):
    venue = models.ForeignKey(
        Venue, on_delete=models.CASCADE, related_name="seats"
    )
    section = models.CharField(max_length=50)
    row = models.CharField(max_length=10)
    number = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["venue", "section", "row", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "section", "row", "number"],
                name="unique_seat_per_venue",
            )
        ]

    def __str__(self):
        return f"{self.section}-{self.row}{self.number} @ {self.venue.name}"


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    event = models.ForeignKey(
        Event, on_delete=models.PROTECT, related_name="reservations"
    )
    seats = models.ManyToManyField(
        Seat, through="ReservationSeat", related_name="reservations"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.CONFIRMED
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"], name="resv_user_status_idx"),
            models.Index(fields=["event", "status"], name="resv_event_status_idx"),
        ]

    def __str__(self):
        return f"Reservation #{self.pk} ({self.status})"


class ReservationSeat(models.Model):
    """Join table between Reservation and Seat.

    The event is stored here as well so the database itself can guarantee
    that a seat can only be held once per event (no double booking).
    Cancelling a reservation deletes its rows, which frees the seats.
    """

    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="reservation_seats"
    )
    seat = models.ForeignKey(
        Seat, on_delete=models.PROTECT, related_name="reservation_seats"
    )
    event = models.ForeignKey(
        Event, on_delete=models.PROTECT, related_name="reservation_seats"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "seat"], name="unique_seat_per_event"
            ),
            models.UniqueConstraint(
                fields=["reservation", "seat"], name="unique_seat_per_reservation"
            ),
        ]

    def clean(self):
        if self.seat.venue_id != self.reservation.event.venue_id:
            raise ValidationError("Seat does not belong to this event's venue.")

    def save(self, *args, **kwargs):
        self.event_id = self.reservation.event_id
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reservation_id} -> {self.seat_id}"
