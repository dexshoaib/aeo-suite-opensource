"""Core views: the health endpoint (liveness + database connectivity)."""

from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """
    GET /api/v1/health/ - liveness + database connectivity probe.

    Unauthenticated by design (infra probe; exposes nothing sensitive).
    200 {"status": "ok", "database": "ok"} when the database answers,
    503 with "error" values when it does not. Keep the body tiny - load
    balancers and CI smoke checks poll this endpoint.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="health",
        tags=["health"],
        responses={
            200: OpenApiResponse(description="Service and database healthy."),
            503: OpenApiResponse(description="Service up, database unreachable."),
        },
    )
    def get(self, request):
        database_ok = self._check_database()
        health = "ok" if database_ok else "error"
        return Response(
            {"status": health, "database": health},
            status=200 if database_ok else 503,
        )

    @staticmethod
    def _check_database() -> bool:
        # Constant probe statement - no interpolation (ADR-0004 rule 6).
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            # Any failure at all means "not healthy" for an infra probe.
            return False
        return True
