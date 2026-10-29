from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from tickets.models import Event, Seat, Venue

User = get_user_model()


def make_client(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


@pytest.fixture
def api_client():
    return make_client()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin",
        email="admin@example.com",
        password="AdminPass12345",
        is_staff=True,
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="alice", email="alice@example.com", password="AlicePass12345"
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="bob", email="bob@example.com", password="BobPass12345"
    )


@pytest.fixture
def admin_client(admin_user):
    return make_client(admin_user)


@pytest.fixture
def user_client(user):
    return make_client(user)


@pytest.fixture
def other_client(other_user):
    return make_client(other_user)


@pytest.fixture
def venue(db):
    return Venue.objects.create(name="Test Arena", address="1 Main Road", city="Durban")


@pytest.fixture
def seats(venue):
    return [Seat.objects.create(venue=venue, section="A", row="B", number=n) for n in (1, 2, 3)]


@pytest.fixture
def event(venue):
    start = timezone.now() + timedelta(days=30)
    return Event.objects.create(
        venue=venue,
        title="Summer Concert",
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        ticket_price=Decimal("150.00"),
    )


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    """Use a fast hasher in tests only; real settings keep Django's default."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
