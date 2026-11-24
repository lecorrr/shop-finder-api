from django.contrib import admin

from imports.models import FeedImport


@admin.register(FeedImport)
class FeedImportAdmin(admin.ModelAdmin):
    list_display = ["id", "shop", "status", "rows_applied", "rows_failed", "created_at"]
    list_filter = ["status"]
    search_fields = ["shop__name", "url", "file_name"]
    exclude = ["content"]
    readonly_fields = [
        "shop",
        "created_by",
        "url",
        "file_name",
        "content_type",
        "status",
        "attempts",
        "content_sha256",
        "rows_total",
        "rows_applied",
        "rows_failed",
        "errors",
        "error",
        "started_at",
        "finished_at",
    ]

    def has_add_permission(self, request) -> bool:
        return False  # imports are created through the API, with a URL or a file

    def get_queryset(self, request):
        return super().get_queryset(request).defer("content")
