from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import set_auth_cookies

User = get_user_model()


@staff_member_required
def admin_impersonate(request, user_id):
    """Linked from UserAdmin's "Impersonate" column (core/admin.py) — the
    only entry point into impersonation, deliberately not exposed anywhere
    in the app itself. A plain Django view (not DRF) since it's reached by
    a normal link click from within /admin/, authenticated via the admin's
    own session rather than a JWT bearer token.

    Mints a real session for the target user — the same httpOnly refresh
    cookie login/register set, on this (the backend's) domain — then
    redirects to the frontend's /impersonate-landing. No access token in
    the URL: the frontend's own auth bootstrap (AuthProvider's mount effect)
    already calls /api/auth/refresh/ using whatever cookie is present, so
    it picks up this new one and signs in as the target user automatically,
    the same path a real login takes — just with the cookie pre-seeded
    instead of a password."""

    target = get_object_or_404(User, id=user_id)
    admin_changelist = reverse('admin:auth_user_changelist')

    if target.is_staff or target.is_superuser:
        messages.error(request, "Can't impersonate a staff/admin account.")
        return HttpResponseRedirect(admin_changelist)

    refresh = RefreshToken.for_user(target)
    response = HttpResponseRedirect(f'{settings.FRONTEND_URL}/impersonate-landing')
    set_auth_cookies(response, str(refresh))
    return response
