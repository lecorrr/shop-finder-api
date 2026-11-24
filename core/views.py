from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.checks import run_checks
from shopfinder import __version__


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "error"])
    version = serializers.CharField()
    checks = serializers.DictField(child=serializers.ChoiceField(choices=["ok", "error"]))


class HealthView(APIView):
    """For uptime checks and the deploy script: 200 when every dependency answers, else 503."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(responses={200: HealthSerializer, 503: HealthSerializer})
    def get(self, request: Request) -> Response:
        checks = run_checks()
        healthy = all(result == "ok" for result in checks.values())
        body = {"status": "ok" if healthy else "error", "version": __version__, "checks": checks}
        code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(body, status=code)
