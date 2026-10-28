from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from helpers import assert_error_schema

pytestmark = pytest.mark.django_db

User = get_user_model()

REGISTER_URL = "/api/auth/register/"
TOKEN_URL = "/api/auth/token/"
REFRESH_URL = "/api/auth/token/refresh/"
ME_URL = "/api/auth/me/"
HEALTH_URL = "/health/"


def test_register_success(api_client):
    response = api_client.post(
        REGISTER_URL,
        {"username": "carol", "email": "carol@example.com", "password": "CarolPass12345"},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "carol"
    assert "password" not in body
    assert User.objects.get(username="carol").check_password("CarolPass12345")


def test_register_duplicate_email_rejected(api_client, user):
    response = api_client.post(
        REGISTER_URL,
        {"username": "other", "email": "ALICE@example.com", "password": "OtherPass12345"},
        format="json",
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "email" in error["details"]


def test_register_duplicate_username_rejected(api_client, user):
    response = api_client.post(
        REGISTER_URL,
        {"username": "alice", "email": "new@example.com", "password": "NewPass12345"},
        format="json",
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "username" in error["details"]


def test_register_weak_password_rejected(api_client):
    response = api_client.post(
        REGISTER_URL,
        {"username": "dave", "email": "dave@example.com", "password": "12345678"},
        format="json",
    )
    assert_error_schema(response, "validation_error", 400)


def test_register_missing_password_rejected(api_client):
    response = api_client.post(
        REGISTER_URL,
        {"username": "erin", "email": "erin@example.com"},
        format="json",
    )
    error = assert_error_schema(response, "validation_error", 400)
    assert "password" in error["details"]


def test_login_returns_tokens(api_client, user):
    response = api_client.post(
        TOKEN_URL,
        {"username": "alice", "password": "AlicePass12345"},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert "access" in body and "refresh" in body


def test_login_wrong_password_rejected(api_client, user):
    response = api_client.post(
        TOKEN_URL,
        {"username": "alice", "password": "WrongPass999"},
        format="json",
    )
    assert_error_schema(response, "authentication_failed", 401)


def test_refresh_returns_new_access_token(api_client, user):
    login = api_client.post(
        TOKEN_URL,
        {"username": "alice", "password": "AlicePass12345"},
        format="json",
    )
    response = api_client.post(
        REFRESH_URL, {"refresh": login.json()["refresh"]}, format="json"
    )
    assert response.status_code == 200
    assert "access" in response.json()


def test_real_jwt_authenticates_requests(api_client, user):
    login = api_client.post(
        TOKEN_URL,
        {"username": "alice", "password": "AlicePass12345"},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
    response = api_client.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_invalid_token_rejected(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    response = api_client.get(ME_URL)
    assert_error_schema(response, "authentication_failed", 401)


def test_me_standard_user(user_client):
    response = user_client.get(ME_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert body["is_staff"] is False


def test_me_admin_user(admin_client):
    response = admin_client.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["is_staff"] is True


def test_me_requires_authentication(api_client):
    response = api_client.get(ME_URL)
    assert_error_schema(response, "authentication_failed", 401)


def test_health_ok_without_authentication(api_client):
    response = api_client.get(HEALTH_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["service"] == "event-ticketing-api"
    assert body["uptime_seconds"] >= 0
    assert "timestamp" in body


def test_health_reports_database_down(api_client):
    with patch("tickets.health.connection") as mock_connection:
        mock_connection.cursor.side_effect = Exception("db down")
        response = api_client.get(HEALTH_URL)
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "down"


def test_unknown_object_returns_standard_404(admin_client):
    response = admin_client.get("/api/venues/9999/")
    assert_error_schema(response, "not_found", 404)
