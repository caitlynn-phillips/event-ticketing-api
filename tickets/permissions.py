from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """Anyone authenticated can read; only admins (is_staff) can write."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_staff


class IsOwnerOrAdmin(permissions.BasePermission):
    """Object-level: the reservation's owner or an admin."""

    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.user_id == request.user.id
