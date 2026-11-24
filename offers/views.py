from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.filters import attribute_filters
from catalog.repository import product_repository, to_api
from offers.models import Offer
from offers.selectors import SearchQuery, search_offers
from offers.serializers import (
    OfferSerializer,
    OfferWriteSerializer,
    SearchQuerySerializer,
    SearchResultSerializer,
)
from offers.services import UnknownProduct, set_offer
from shops.models import Shop
from stats.services import record_search


def offer_row(offer: Offer, products: dict[str, dict], *, with_shop: bool) -> dict:
    document = products.get(offer.product_id)
    row = {
        "product": None if document is None else to_api(document),
        "price": offer.price,
        "quantity": offer.quantity,
        "updated_at": offer.updated_at,
    }
    if with_shop:
        row["shop"] = {
            "id": offer.shop_id,
            "name": offer.shop.name,
            "address": offer.shop.address,
            "latitude": offer.shop.latitude,
            "longitude": offer.shop.longitude,
            "distance_km": round(offer.distance_km, 2),
        }
    return row


class ShopOfferListView(generics.ListAPIView):
    """A shop's offers, cheapest first, with their products."""

    serializer_class = OfferSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no URL kwargs
            return Offer.objects.none()
        shop = get_object_or_404(Shop, pk=self.kwargs["shop_id"], is_active=True)
        return shop.offers.order_by("price", "id")

    def list(self, request: Request, *args, **kwargs) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        products = product_repository().get_many([offer.product_id for offer in page])
        rows = [offer_row(offer, products, with_shop=False) for offer in page]
        return self.get_paginated_response(OfferSerializer(rows, many=True).data)


class ShopOfferDetailView(APIView):
    """The owner sets or removes the price and stock of one product in their shop."""

    permission_classes = [permissions.IsAuthenticated]

    def shop(self, request: Request, shop_id: int) -> Shop:
        return get_object_or_404(Shop, pk=shop_id, owner=request.user)

    @extend_schema(request=OfferWriteSerializer, responses=OfferSerializer)
    def put(self, request: Request, shop_id: int, product_id: str) -> Response:
        shop = self.shop(request, shop_id)
        data = OfferWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        products = product_repository()
        try:
            offer, created = set_offer(
                shop=shop, product_id=product_id, products=products, **data.validated_data
            )
        except UnknownProduct as error:
            raise serializers.ValidationError({"product_id": ["no such product"]}) from error
        row = offer_row(offer, products.get_many([product_id]), with_shop=False)
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(OfferSerializer(row).data, status=code)

    @extend_schema(responses={204: None, 404: None})
    def delete(self, request: Request, shop_id: int, product_id: str) -> Response:
        shop = self.shop(request, shop_id)
        deleted, _ = Offer.objects.filter(shop=shop, product_id=product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND)


@extend_schema(
    parameters=[
        SearchQuerySerializer,
        OpenApiParameter("attr.<name>", str, description="Attribute filter, needs category"),
    ],
    responses=SearchResultSerializer(many=True),
)
class SearchView(generics.GenericAPIView):
    """Where can I buy this nearby? Nearest shops first, then the cheapest."""

    permission_classes = [permissions.AllowAny]
    serializer_class = SearchResultSerializer
    queryset = Offer.objects.none()  # for the schema; the real one is built per request

    def get(self, request: Request) -> Response:
        params = SearchQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        query = SearchQuery(
            **params.validated_data,
            attributes=attribute_filters(request, params.validated_data.get("category")),
        )
        offers, products = search_offers(query, product_repository())
        page = self.paginate_queryset(offers)
        rows = [offer_row(offer, products, with_shop=True) for offer in page]
        record_search(
            q=query.q,
            category=query.category,
            lat=query.lat,
            lon=query.lon,
            radius_km=query.radius_km,
            results=self.paginator.page.paginator.count,  # across all pages
        )
        return self.get_paginated_response(SearchResultSerializer(rows, many=True).data)
