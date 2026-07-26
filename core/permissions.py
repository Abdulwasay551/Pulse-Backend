from rest_framework.permissions import BasePermission


def is_hr_or_legacy(request):
    """True for HR-role users *and* for pre-existing accounts that predate
    the role system (no profile row at all) — a missing profile means
    "full access", never "no access", so nothing that worked before this
    feature shipped starts failing."""
    profile = getattr(request.user, 'profile', None)
    return profile is None or profile.role == 'HR'


class IsOwner(BasePermission):
    """Every per-user object across every module app is scoped to the user
    who created it — this is the entire authorization model, shared rather
    than duplicated per app. Also gates every action (list/create/etc, via
    has_permission) to HR-role accounts — Employee-role logins get none of
    the full CRUD modules, only the narrow self-service endpoints in
    core/my_views.py."""

    def has_permission(self, request, view):
        return is_hr_or_legacy(request)

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id


class IsHR(BasePermission):
    """For the handful of viewsets that scope ownership through a parent
    object instead of their own `owner` field (EmployeeDocument,
    SurveyResponse, Enrollment, OnboardingTask, OffboardingTask, and the
    read-only dashboard-summary views) — same HR-only gate as IsOwner,
    without the object-level owner check those don't need."""

    def has_permission(self, request, view):
        return is_hr_or_legacy(request)
