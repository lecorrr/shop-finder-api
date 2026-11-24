from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from shops.models import Shop
from shops.permissions import IsOwnerOrReadOnly
from shops.selectors import shops_near
from shops.serializers import NearQuerySerializer, ShopSerializer


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("lat", float, description="Latitude; with lon, lists shops nearby"),
            OpenApiParameter("lon", float, description="Longitude"),
            OpenApiParameter("radius_km", float, description="0.1 to 50, default 2"),
            OpenApiParameter("q", str, description="Part of the shop's name"),
        ]
    ),
    mine=extend_schema(responses=ShopSerializer(many=True)),
)
class ShopViewSet(viewsets.ModelViewSet):
    serializer_class = ShopSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def get_queryset(self):
        if self.request.method not in permissions.SAFE_METHODS:
            # Owners change only their own shops; anyone else's shop is a 404, not a 403.
            return Shop.objects.filter(owner_id=self.request.user.id).select_related("owner")
        params = self.request.query_params
        if "lat" in params or "lon" in params:
            near = NearQuerySerializer(data=params)
            near.is_valid(raise_exception=True)
            queryset = shops_near(**near.validated_data)
        else:
            queryset = Shop.objects.filter(is_active=True)
        if name := params.get("q", "").strip():
            queryset = queryset.filter(name__icontains=name)
        return queryset.select_related("owner")

    def perform_create(self, serializer) -> None:
        serializer.save(owner=self.request.user)

    def destroy(self, request, *args, **kwargs) -> Response:
        """Closing a shop hides it; its offers and import history stay for the record."""
        shop = self.get_object()
        shop.is_active = False
        shop.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, permission_classes=[permissions.IsAuthenticated])
    def mine(self, request) -> Response:
        shops = Shop.objects.filter(owner=request.user).select_related("owner")
        page = self.paginate_queryset(shops)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)
