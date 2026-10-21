from django.db import transaction
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class VenueViewSet(viewsets.ModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [IsAdminOrReadOnly]


class SeatViewSet(viewsets.ModelViewSet):
    serializer_class = SeatSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = Seat.objects.select_related("venue")
        venue_id = self.request.query_params.get("venue")
        if venue_id:
            queryset = queryset.filter(venue_id=venue_id)
        return queryset


class EventViewSet(viewsets.ModelViewSet):
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
        queryset = Reservation.objects.select_related(
            "user", "event"
        ).prefetch_related("seats")
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        if reservation.status == Reservation.Status.CANCELLED:
            return Response(
                {"detail": "Reservation is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            reservation.reservation_seats.all().delete()
            reservation.status = Reservation.Status.CANCELLED
            reservation.save(update_fields=["status"])
        return Response(self.get_serializer(reservation).data)
