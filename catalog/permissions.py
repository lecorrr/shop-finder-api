from rest_framework import permissions


class IsStaffOrReadOnly(permissions.BasePermission):
    """The catalogue is curated: anyone reads it, only staff change it."""

    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)
