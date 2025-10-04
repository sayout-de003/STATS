# apps/users/permissions.py
from rest_framework import permissions

class IsAdmin(permissions.BasePermission):
    """
    Allows access only to admin users.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_admin


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to view/edit it.
    Works with models that have a `user` field.
    """
    def has_object_permission(self, request, view, obj):
        # For objects tied to a specific user
        if hasattr(obj, "user"):
            return obj.user == request.user or (request.user and request.user.is_admin)
        # If no `user` attr, fallback to admin-only
        return request.user and request.user.is_admin

    def has_permission(self, request, view):
        # Allow safe methods for authenticated users, otherwise admin only
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_admin
