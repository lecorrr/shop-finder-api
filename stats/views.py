from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopfinder import mongo
from stats.repository import SearchEventRepository
from stats.serializers import MostWantedQuerySerializer, MostWantedSerializer


class MostWantedView(APIView):
    """For shop owners: what people search for nearby, and what nobody nearby sells."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        parameters=[MostWantedQuerySerializer], responses=MostWantedSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        query = MostWantedQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        options = dict(query.validated_data)
        unmet_only = options.pop("unmet")
        rows = SearchEventRepository(mongo.database()).most_wanted(**options, unmet_only=unmet_only)
        return Response(MostWantedSerializer(rows, many=True).data)
