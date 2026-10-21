from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EventViewSet,
    MeView,
    RegisterView,
    ReservationViewSet,
    SeatViewSet,
    VenueViewSet,
)

router = DefaultRouter()
router.register("venues", VenueViewSet, basename="venue")
router.register("seats", SeatViewSet, basename="seat")
router.register("events", EventViewSet, basename="event")
router.register("reservations", ReservationViewSet, basename="reservation")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
