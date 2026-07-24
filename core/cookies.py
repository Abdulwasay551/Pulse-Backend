from django.conf import settings


def set_auth_cookies(response, refresh_token: str):
    """Attaches the httpOnly refresh-token cookie plus its non-httpOnly
    "a session might exist" flag (see SIMPLE_JWT / AUTH_COOKIE_* comments in
    settings.py for why there are two cookies, not one).
    """
    max_age = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
    common = {
        'max_age': max_age,
        'samesite': settings.AUTH_COOKIE_SAMESITE,
        'secure': settings.AUTH_COOKIE_SECURE,
        'path': '/',
    }
    response.set_cookie(settings.AUTH_COOKIE_NAME, refresh_token, httponly=True, **common)
    response.set_cookie(settings.AUTH_SESSION_FLAG_COOKIE_NAME, '1', httponly=False, **common)
    return response


def clear_auth_cookies(response):
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path='/', samesite=settings.AUTH_COOKIE_SAMESITE)
    response.delete_cookie(settings.AUTH_SESSION_FLAG_COOKIE_NAME, path='/', samesite=settings.AUTH_COOKIE_SAMESITE)
    return response
