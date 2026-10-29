from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Event, Reservation, ReservationSeat, Seat, Venue

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def validate_email(self, value):
        if not value:
            raise serializers.ValidationError("Email is required.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already in use.")
        return value

    def validate(self, attrs):
        candidate = User(username=attrs.get("username", ""), email=attrs.get("email", ""))
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff"]
        read_only_fields = fields


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["id", "name", "address", "city", "created_at"]
        read_only_fields = ["id", "created_at"]


class SeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seat
        fields = ["id", "venue", "section", "row", "number"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        # The DB constraint also enforces this; this gives a clean 400.
        venue = attrs.get("venue", getattr(self.instance, "venue", None))
        section = attrs.get("section", getattr(self.instance, "section", None))
        row = attrs.get("row", getattr(self.instance, "row", None))
        number = attrs.get("number", getattr(self.instance, "number", None))
        duplicates = Seat.objects.filter(venue=venue, section=section, row=row, number=number)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("This seat already exists for the venue.")
        return attrs


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "venue",
            "title",
            "description",
            "starts_at",
            "ends_at",
            "ticket_price",
            "is_published",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "ends_at must be after starts_at."})
        return attrs


class ReservationSerializer(serializers.ModelSerializer):
    seat_ids = serializers.PrimaryKeyRelatedField(
        queryset=Seat.objects.all(),
        many=True,
        write_only=True,
        allow_empty=False,
    )
    seats = SeatSerializer(many=True, read_only=True)
    user = serializers.ReadOnlyField(source="user.username")

    class Meta:
        model = Reservation
        fields = [
            "id",
            "user",
            "event",
            "seat_ids",
            "seats",
            "status",
            "total_price",
            "created_at",
        ]
        read_only_fields = ["id", "user", "status", "total_price", "created_at"]

    def validate_event(self, event):
        if not event.is_published:
            raise serializers.ValidationError("This event is not available.")
        if event.starts_at <= timezone.now():
            raise serializers.ValidationError("This event has already started.")
        return event

    def validate(self, attrs):
        event = attrs["event"]
        seats = attrs["seat_ids"]

        if len({seat.pk for seat in seats}) != len(seats):
            raise serializers.ValidationError({"seat_ids": "Duplicate seats in request."})

        wrong_venue = [s.pk for s in seats if s.venue_id != event.venue_id]
        if wrong_venue:
            raise serializers.ValidationError(
                {"seat_ids": f"Seats not in this event's venue: {wrong_venue}"}
            )

        taken = ReservationSeat.objects.filter(event=event, seat__in=seats).values_list(
            "seat_id", flat=True
        )
        if taken:
            raise serializers.ValidationError(
                {"seat_ids": f"Seats already reserved: {sorted(taken)}"}
            )
        return attrs

    def create(self, validated_data):
        seats = validated_data.pop("seat_ids")
        event = validated_data["event"]
        total = event.ticket_price * Decimal(len(seats))
        try:
            with transaction.atomic():
                reservation = Reservation.objects.create(
                    user=self.context["request"].user,
                    event=event,
                    total_price=total,
                    status=Reservation.Status.CONFIRMED,
                )
                ReservationSeat.objects.bulk_create(
                    [
                        ReservationSeat(reservation=reservation, seat=seat, event=event)
                        for seat in seats
                    ]
                )
        except IntegrityError:
            # Another request grabbed a seat between validation and insert.
            raise serializers.ValidationError({"seat_ids": "One or more seats were just reserved."})
        return reservation
