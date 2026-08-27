"""Personal API token issuance + authentication. A token is a high-entropy
random secret (not a password), so a straight SHA-256 hash is enough to
store safely — no need for bcrypt/PBKDF2's deliberate slowness, which
exists specifically to slow down guessing low-entropy human passwords."""

import hashlib
import secrets

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import ApiToken

_PREFIX = 'plsat_'


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def generate_token(user, label: str = '') -> tuple[ApiToken, str]:
    """Returns (ApiToken row, plaintext token) — the plaintext is only ever
    available here, at creation; only its hash is persisted."""
    raw = _PREFIX + secrets.token_urlsafe(32)
    token = ApiToken.objects.create(
        user=user, label=label, prefix=raw[:8], hashed_token=_hash(raw)
    )
    return token, raw


class ApiTokenAuthentication(BaseAuthentication):
    """Tried before JWTAuthentication in DEFAULT_AUTHENTICATION_CLASSES.
    Returns None (not an error) for anything that isn't shaped like one of
    our tokens, so normal JWT-bearing frontend requests fall through to
    JWTAuthentication with only a cheap prefix check's worth of overhead."""

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer ') or not auth_header[7:].startswith(_PREFIX):
            return None
        raw = auth_header[7:]

        try:
            token = ApiToken.objects.select_related('user').get(hashed_token=_hash(raw), revoked_at__isnull=True)
        except ApiToken.DoesNotExist:
            raise AuthenticationFailed('Invalid or revoked API token.')

        ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return (token.user, None)
