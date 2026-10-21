import time

from django.db import connection
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

STARTED_AT = time.monotonic()
STARTED_AT_UTC = timezone.now()


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            database = "up"
        except Exception:
            database = "down"

        healthy = database == "up"
        body = {
            "status": "ok" if healthy else "degraded",
            "service": "event-ticketing-api",
            "database": database,
            "uptime_seconds": round(time.monotonic() - STARTED_AT, 2),
            "started_at": STARTED_AT_UTC.isoformat(),
            "timestamp": timezone.now().isoformat(),
        }
        return Response(
            body,
            status=status.HTTP_200_OK
            if healthy
            else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
