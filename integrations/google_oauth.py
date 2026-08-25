"""Google Calendar + Meet — the one true-OAuth integration in this app.
Every other integration in this package is BYOK (the org pastes its own
API key/webhook URL); Google Calendar has no such per-org static
credential, so this uses one Pulse-owned OAuth client
(settings.GOOGLE_OAUTH_CLIENT_ID/SECRET) that each org individually
authorizes via Google's real consent screen.

Getting a Meet link onto a calendar event needs only the standard Calendar
API's conferenceData field (conferenceSolutionKey type "hangoutsMeet") —
not the newer standalone Google Meet REST API, which is a different,
Workspace-billing-gated product. That distinction is what keeps this
feature usable on the free/no-billing Calendar API quota.
"""

import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone

_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
_TOKEN_URL = 'https://oauth2.googleapis.com/token'
_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
_CALENDAR_EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'

# calendar.events is enough to create/read events (and their attached Meet
# link) without asking for broader calendar management the org doesn't
# need for this feature.
SCOPES = 'https://www.googleapis.com/auth/calendar.events'

_STATE_SALT = 'integrations.google_oauth'


class GoogleOAuthError(Exception):
    pass


def build_auth_url(owner_id, redirect_uri):
    """Called from an authenticated API request (so we know owner_id);
    returns the URL the frontend then navigates the browser to. `state` is
    a signed, time-limited token — the callback below is unauthenticated
    (Google, not our own frontend, calls it), so this is how it safely
    recovers which org is connecting without trusting an unsigned value."""
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        raise GoogleOAuthError('Google integration is not configured on this deployment yet.')
    state = signing.dumps(owner_id, salt=_STATE_SALT)
    params = {
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPES,
        'access_type': 'offline',
        # Forces Google to return a refresh_token even if this org
        # authorized before — without it, a re-connect after revoking
        # access silently comes back with no refresh_token at all.
        'prompt': 'consent',
        'state': state,
    }
    query = '&'.join(f'{k}={requests.utils.quote(str(v))}' for k, v in params.items())
    return f'{_AUTH_URL}?{query}'


def verify_state(state: str):
    """Returns the owner_id encoded in build_auth_url's state, or raises if
    it's missing, tampered with, or older than 10 minutes."""
    try:
        return signing.loads(state, salt=_STATE_SALT, max_age=600)
    except signing.BadSignature as exc:
        raise GoogleOAuthError('This connection link is invalid or expired — try connecting again.') from exc


def exchange_code_for_tokens(code, redirect_uri):
    resp = requests.post(
        _TOKEN_URL,
        data={
            'code': code,
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
        timeout=10,
    )
    if not resp.ok:
        raise GoogleOAuthError(f'Google rejected the connection attempt: {resp.text[:200]}')
    return resp.json()


def _fetch_email(access_token):
    resp = requests.get(_USERINFO_URL, headers={'Authorization': f'Bearer {access_token}'}, timeout=8)
    return resp.json().get('email', '') if resp.ok else ''


def save_connection(owner_id, token_data):
    from .models import GoogleOAuthConnection

    access_token = token_data['access_token']
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in', 3600)
    email = _fetch_email(access_token)

    conn, _ = GoogleOAuthConnection.objects.get_or_create(owner_id=owner_id, defaults={'token_expires_at': timezone.now()})
    conn.set_access_token(access_token)
    if refresh_token:
        # Google only sends this on first consent (or with prompt=consent,
        # which build_auth_url always sets) — keep the existing one on the
        # rare response that omits it rather than clobbering with nothing.
        conn.set_refresh_token(refresh_token)
    conn.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    conn.google_email = email
    conn.scope = token_data.get('scope', '')
    conn.save()
    return conn


def _refresh_access_token(conn):
    resp = requests.post(
        _TOKEN_URL,
        data={
            'refresh_token': conn.get_refresh_token(),
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'grant_type': 'refresh_token',
        },
        timeout=10,
    )
    if not resp.ok:
        raise GoogleOAuthError(f'Could not refresh the Google connection — reconnect it: {resp.text[:200]}')
    data = resp.json()
    conn.set_access_token(data['access_token'])
    conn.token_expires_at = timezone.now() + timedelta(seconds=data.get('expires_in', 3600))
    conn.save(update_fields=['encrypted_access_token', 'token_expires_at', 'updated_at'])
    return conn


def get_connection(owner_id):
    from .models import GoogleOAuthConnection

    return GoogleOAuthConnection.objects.filter(owner_id=owner_id).first()


def _get_valid_access_token(owner_id):
    conn = get_connection(owner_id)
    if not conn:
        raise GoogleOAuthError('Google Calendar is not connected. Connect it under Settings -> Integrations first.')
    if conn.token_expires_at <= timezone.now() + timedelta(minutes=1):
        conn = _refresh_access_token(conn)
    return conn.get_access_token()


def create_calendar_event_with_meet(owner_id, summary, description, start_dt, end_dt, attendee_emails=None):
    """Creates a real Calendar event with a Google Meet link attached.
    start_dt/end_dt are timezone-aware datetimes. Returns
    {event_link, meet_link}."""
    access_token = _get_valid_access_token(owner_id)
    payload = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': start_dt.isoformat()},
        'end': {'dateTime': end_dt.isoformat()},
        'attendees': [{'email': e} for e in (attendee_emails or [])],
        'conferenceData': {
            'createRequest': {
                'requestId': str(uuid.uuid4()),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
            }
        },
    }
    resp = requests.post(
        _CALENDAR_EVENTS_URL,
        params={'conferenceDataVersion': 1, 'sendUpdates': 'all'},
        headers={'Authorization': f'Bearer {access_token}'},
        json=payload,
        timeout=10,
    )
    if not resp.ok:
        raise GoogleOAuthError(f'Could not create the calendar event: {resp.text[:200]}')
    data = resp.json()
    meet_link = ''
    for entry_point in data.get('conferenceData', {}).get('entryPoints', []):
        if entry_point.get('entryPointType') == 'video':
            meet_link = entry_point.get('uri', '')
            break
    return {'event_link': data.get('htmlLink', ''), 'meet_link': meet_link}


def disconnect(owner_id):
    from .models import GoogleOAuthConnection

    GoogleOAuthConnection.objects.filter(owner_id=owner_id).delete()
