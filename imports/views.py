from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from imports.fetch import MAX_BYTES
from imports.models import FeedImport
from imports.serializers import FeedImportCreateSerializer, FeedImportSerializer
from imports.tasks import queue_import
from shops.models import Shop

# Room for the multipart boundaries and headers around a file of MAX_BYTES.
MAX_REQUEST_BYTES = MAX_BYTES + 64 * 1024


class PayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "the feed is larger than 5 MB"
    default_code = "payload_too_large"


class ShopImportListCreateView(generics.ListCreateAPIView):
    """A shop owner loads prices and stock from a feed; the work happens in a Celery worker."""

    serializer_class = FeedImportSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser]
    throttle_scope = "imports"

    def get_throttles(self):
        if self.request.method == "POST":
            return [*super().get_throttles(), ScopedRateThrottle()]
        return super().get_throttles()

    def shop(self) -> Shop:
        return get_object_or_404(Shop, pk=self.kwargs["shop_id"], owner=self.request.user)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no URL kwargs
            return FeedImport.objects.none()
        return self.shop().imports.defer("content")

    @extend_schema(request=FeedImportCreateSerializer, responses={202: FeedImportSerializer})
    def post(self, request: Request, shop_id: int) -> Response:
        # Refuse before Django reads a huge body into memory or a temp file.
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_REQUEST_BYTES:
            raise PayloadTooLarge
        shop = self.shop()
        data = FeedImportCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data.get("file")
        with transaction.atomic():
            feed = FeedImport.objects.create(
                shop=shop,
                created_by=request.user,
                url=data.validated_data.get("url", ""),
                file_name=upload.name if upload else "",
                content=upload.read() if upload else None,
                content_type=upload.content_type if upload else "",
            )
            transaction.on_commit(lambda: queue_import(feed.pk))
        feed = FeedImport.objects.defer("content").get(pk=feed.pk)
        return Response(FeedImportSerializer(feed).data, status=status.HTTP_202_ACCEPTED)


class FeedImportDetailView(generics.RetrieveAPIView):
    serializer_class = FeedImportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FeedImport.objects.filter(shop__owner=self.request.user).defer("content")
