from dataclasses import dataclass

from rest_framework import pagination, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param


class PageNumberPagination(pagination.PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


class PageQuerySerializer(serializers.Serializer):
    """Page parameters for lists that come from MongoDB rather than a queryset."""

    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=PageNumberPagination.max_page_size, default=20
    )


@dataclass(frozen=True)
class Page:
    number: int
    size: int

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size


def read_page(request: Request) -> Page:
    query = PageQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    return Page(query.validated_data["page"], query.validated_data["page_size"])


def page_response(request: Request, page: Page, results: list, total: int) -> Response:
    """The same envelope DRF's PageNumberPagination returns for querysets."""
    url = request.build_absolute_uri()
    has_next = page.offset + len(results) < total
    return Response(
        {
            "count": total,
            "next": replace_query_param(url, "page", page.number + 1) if has_next else None,
            "previous": replace_query_param(url, "page", page.number - 1)
            if page.number > 1
            else None,
            "results": results,
        }
    )
