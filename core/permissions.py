from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Every per-user object across every module app is scoped to the user
    who created it — no shared/team data model exists (yet), so this is the
    entire authorization model, shared rather than duplicated per app."""

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id
