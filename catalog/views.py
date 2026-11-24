from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response

from catalog.filters import attribute_filters
from catalog.permissions import IsStaffOrReadOnly
from catalog.repository import ACTIVE, DuplicateBarcode, product_repository, to_api
from catalog.serializers import (
    ProductPageSerializer,
    ProductQuerySerializer,
    ProductSerializer,
    ProductWriteSerializer,
)
from core.pagination import PageQuerySerializer, page_response, read_page

WRITABLE_FIELDS = ("name", "brand", "category", "barcode", "attributes", "tags")


def duplicate_barcode_error(error: DuplicateBarcode) -> serializers.ValidationError:
    return serializers.ValidationError({"barcode": [f"{error} is already in the catalogue"]})


class ProductViewSet(viewsets.ViewSet):
    """The shared catalogue: anyone can read it, staff maintain it."""

    permission_classes = [IsStaffOrReadOnly]
    parser_classes = [JSONParser]
    lookup_value_regex = "[0-9a-f]{24}"

    @extend_schema(
        parameters=[
            ProductQuerySerializer,
            PageQuerySerializer,
            OpenApiParameter("attr.<name>", str, description="Attribute filter, needs category"),
        ],
        responses=ProductPageSerializer,
    )
    def list(self, request: Request) -> Response:
        query = ProductQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        category = query.validated_data.get("category")
        page = read_page(request)
        products, total = product_repository().search(
            text=query.validated_data.get("q"),
            category=category,
            attributes=attribute_filters(request, category),
            limit=page.size,
            offset=page.offset,
        )
        results = ProductSerializer([to_api(doc) for doc in products], many=True).data
        return page_response(request, page, results, total)

    @extend_schema(responses=ProductSerializer)
    def retrieve(self, request: Request, pk: str) -> Response:
        document = product_repository().get(pk)
        if document is None or (document["status"] != ACTIVE and not request.user.is_staff):
            raise NotFound("no such product")
        return Response(ProductSerializer(to_api(document)).data)

    @extend_schema(request=ProductWriteSerializer, responses={201: ProductSerializer})
    def create(self, request: Request) -> Response:
        data = ProductWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            document = product_repository().create(data.validated_data)
        except DuplicateBarcode as error:
            raise duplicate_barcode_error(error) from error
        return Response(ProductSerializer(to_api(document)).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ProductWriteSerializer, responses=ProductSerializer)
    def partial_update(self, request: Request, pk: str) -> Response:
        if not isinstance(request.data, dict):
            raise serializers.ValidationError({"non_field_errors": ["expected a JSON object"]})
        repository = product_repository()
        current = repository.get(pk)
        if current is None:
            raise NotFound("no such product")
        # Validate the product as it will be, so a new category is checked with its attributes.
        stored = to_api(current)
        merged = {key: stored[key] for key in WRITABLE_FIELDS} | request.data
        data = ProductWriteSerializer(data=merged)
        data.is_valid(raise_exception=True)
        try:
            document = repository.update(pk, data.validated_data)
        except DuplicateBarcode as error:
            raise duplicate_barcode_error(error) from error
        if document is None:
            raise NotFound("no such product")
        return Response(ProductSerializer(to_api(document)).data)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, pk: str) -> Response:
        """Archived, not deleted: offers keep pointing at a product that still exists."""
        if not product_repository().archive(pk):
            raise NotFound("no such product")
        return Response(status=status.HTTP_204_NO_CONTENT)
