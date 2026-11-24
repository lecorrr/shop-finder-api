from django.contrib import admin
from django.urls import include, path, register_converter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from catalog.views import ProductViewSet
from core.converters import ObjectIdConverter
from core.views import HealthView
from imports.views import FeedImportDetailView, ShopImportListCreateView
from offers.views import SearchView, ShopOfferDetailView, ShopOfferListView
from shops.views import ShopViewSet
from stats.views import MostWantedView

register_converter(ObjectIdConverter, "objectid")

router = DefaultRouter()
router.register("shops", ShopViewSet, basename="shop")
router.register("products", ProductViewSet, basename="product")

api = [
    path("", include(router.urls)),
    path("auth/", include("accounts.urls")),
    path("search/", SearchView.as_view(), name="search"),
    path("shops/<int:shop_id>/offers/", ShopOfferListView.as_view(), name="shop-offers"),
    path(
        "shops/<int:shop_id>/offers/<objectid:product_id>/",
        ShopOfferDetailView.as_view(),
        name="shop-offer",
    ),
    path("shops/<int:shop_id>/imports/", ShopImportListCreateView.as_view(), name="shop-imports"),
    path("imports/<int:pk>/", FeedImportDetailView.as_view(), name="import-detail"),
    path("stats/most-wanted/", MostWantedView.as_view(), name="most-wanted"),
    path("health/", HealthView.as_view(), name="health"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api)),
]
