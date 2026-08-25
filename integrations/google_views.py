from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsHR, IsOwner, owner_scope_id

from .google_oauth import (
    GoogleOAuthError,
    build_auth_url,
    disconnect,
    exchange_code_for_tokens,
    get_connection,
    save_connection,
    verify_state,
)

# Must exactly match an "Authorized redirect URI" configured on the Google
# Cloud OAuth client (settings.GOOGLE_OAUTH_CLIENT_ID) — Google rejects the
# whole flow with redirect_uri_mismatch otherwise. Built from FRONTEND_URL's
# API counterpart isn't reliable across environments, so this is computed
# from the request itself at call time (see _redirect_uri below) rather
# than hardcoded, so it's automatically correct on whatever host actually
# served the request (production custom domain, its .vercel.app alias, or
# localhost during development) as long as that exact host is registered.
def _redirect_uri(request):
    return request.build_absolute_uri('/api/integrations/google/callback/')


class GoogleConnectUrlView(APIView):
    """Authenticated (so we know owner_id) — returns the URL to redirect
    the browser to; the frontend does `window.location.href = auth_url`
    itself rather than this endpoint redirecting directly, since a plain
    browser navigation here wouldn't carry the Bearer token this app's
    auth relies on."""

    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def get(self, request):
        try:
            auth_url = build_auth_url(owner_scope_id(request), _redirect_uri(request))
        except GoogleOAuthError as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'auth_url': auth_url})


class GoogleCallbackView(APIView):
    """Google redirects the browser here after consent — unauthenticated by
    necessity (Google doesn't send our Bearer token), state carries the
    signed owner_id instead. Ends by redirecting the browser back to the
    frontend settings page with a query param the UI reads to show a
    success/error toast."""

    permission_classes = [AllowAny]

    def get(self, request):
        settings_url = f'{settings.FRONTEND_URL}/dashboard/settings/integrations'
        error = request.query_params.get('error')
        if error:
            return HttpResponseRedirect(f'{settings_url}?google=error&detail={error}')

        code = request.query_params.get('code')
        state = request.query_params.get('state')
        if not code or not state:
            return HttpResponseRedirect(f'{settings_url}?google=error&detail=missing_code')

        try:
            owner_id = verify_state(state)
            token_data = exchange_code_for_tokens(code, _redirect_uri(request))
            save_connection(owner_id, token_data)
        except GoogleOAuthError as exc:
            return HttpResponseRedirect(f'{settings_url}?google=error&detail={exc}')

        return HttpResponseRedirect(f'{settings_url}?google=connected')


class GoogleStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        conn = get_connection(owner_scope_id(request))
        return Response({'connected': conn is not None, 'email': conn.google_email if conn else None})


class GoogleDisconnectView(APIView):
    permission_classes = [IsAuthenticated, IsOwner | IsHR]

    def post(self, request):
        disconnect(owner_scope_id(request))
        return Response({'detail': 'Disconnected.'})
