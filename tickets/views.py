from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import generics, mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .exceptions import Conflict
from .models import Event, Reservation, Seat, Venue
from .permissions import IsAdminOrReadOnly, IsOwnerOrAdmin
from .serializers import (
    EventSerializer,
    RegisterSerializer,
    ReservationSerializer,
    SeatSerializer,
    UserSerializer,
    VenueSerializer,
)


class ProtectedDeleteMixin:
    """Return 409 instead of 500 when other records still depend on this one."""

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise Conflict("Cannot delete this record because other records depend on it.")


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class VenueViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [IsAdminOrReadOnly]


class SeatViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    serializer_class = SeatSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = Seat.objects.select_related("venue")
        venue_id = self.request.query_params.get("venue")
        if venue_id:
            queryset = queryset.filter(venue_id=venue_id)
        return queryset


class EventViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = Event.objects.select_related("venue")
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_published=True)
        venue_id = self.request.query_params.get("venue")
        if venue_id:
            queryset = queryset.filter(venue_id=venue_id)
        return queryset


class ReservationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Standard users see and manage only their own reservations.

    Admins see all. DELETE removes the reservation; POST .../cancel/ keeps
    the record but marks it cancelled. Both free the seats.
    """

    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        queryset = Reservation.objects.select_related("user", "event").prefetch_related("seats")
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        if reservation.status == Reservation.Status.CANCELLED:
            raise ValidationError("Reservation is already cancelled.")
        with transaction.atomic():
            reservation.reservation_seats.all().delete()
            reservation.status = Reservation.Status.CANCELLED
            reservation.save(update_fields=["status"])
        reservation = self.get_queryset().get(pk=reservation.pk)
        return Response(self.get_serializer(reservation).data)
