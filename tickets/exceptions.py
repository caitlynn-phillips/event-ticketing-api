import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)

ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "validation_error",
    status.HTTP_401_UNAUTHORIZED: "authentication_failed",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
}


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with existing data."
    default_code = "conflict"


def build_error(code, message, status_code, details=None):
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "status": status_code,
        }
    }


def custom_exception_handler(exc, context):
    """Return every error in one standard JSON schema."""
    response = exception_handler(exc, context)

    if response is None:
        # Unhandled exception: log it, return a safe generic 500.
        logger.exception("Unhandled exception", exc_info=exc)
        return Response(
            build_error(
                "server_error",
                "An unexpected error occurred.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = ERROR_CODES.get(response.status_code, "error")

    if response.status_code == status.HTTP_400_BAD_REQUEST:
        message = "Validation failed."
        details = response.data
    else:
        data = response.data
        message = data.get("detail") if isinstance(data, dict) else None
        message = str(message) if message else "Request failed."
        details = None

    response.data = build_error(code, message, response.status_code, details)
    return response
