from django.conf import settings
from django.db import models
from django.db.models import Q

from shops.models import Shop


class FeedImport(models.Model):
    """A shop's price and stock list, loaded in the background from a URL or an upload."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        DONE = "done"
        UNCHANGED = "unchanged"
        FAILED = "failed"

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="imports")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    url = models.URLField(max_length=500, blank=True)
    file_name = models.CharField(max_length=200, blank=True)
    # An upload is kept only until it is processed.
    content = models.BinaryField(null=True, editable=False)
    content_type = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    content_sha256 = models.CharField(max_length=64, blank=True)
    rows_total = models.PositiveIntegerField(default=0)
    rows_applied = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(url="") | ~Q(file_name=""), name="import_has_a_source"
            )
        ]

    def __str__(self) -> str:
        return f"import {self.pk} for {self.shop}"
