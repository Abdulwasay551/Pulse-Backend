"""Google Workspace Device Management — a service account with domain-wide
delegation, entirely self-serve on the connecting org's side: their own
Workspace Super Admin creates the service account in their own Google
Cloud project AND authorizes its domain-wide delegation in their own
Admin console (both steps require that same super-admin role — no Google
approval of Pulse needed, unlike a published OAuth app). Architecturally
different from the existing google_oauth.py (a user-consent redirect
against one Pulse-owned OAuth client shared by every org) — this is a
server-to-server JWT Bearer flow using each org's own service account
credentials, so it fits this generic BYOK catalog instead.

Confirmed live: oauth2.googleapis.com/token genuinely rejects a fake JWT
assertion, and the Admin SDK's device-list endpoint genuinely rejects a
fake bearer token."""

import json
import time

import jwt
import requests

_TOKEN_URL = 'https://oauth2.googleapis.com/token'
_API_BASE = 'https://admin.googleapis.com/admin/directory/v1'
_SCOPES = (
    'https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly '
    'https://www.googleapis.com/auth/admin.directory.device.mobile.readonly'
)


class GoogleWorkspaceDevicesError(Exception):
    pass


def _get_access_token(config):
    try:
        key_data = json.loads(config['service_account_json'])
    except (KeyError, json.JSONDecodeError) as exc:
        raise GoogleWorkspaceDevicesError('That doesn\'t look like a valid service account JSON key file.') from exc

    delegated_admin = config.get('delegated_admin_email', '').strip()
    if not delegated_admin:
        raise GoogleWorkspaceDevicesError('A delegated admin email is required.')

    now = int(time.time())
    claims = {
        'iss': key_data.get('client_email'),
        'scope': _SCOPES,
        'aud': _TOKEN_URL,
        'iat': now,
        'exp': now + 3600,
        'sub': delegated_admin,
    }
    try:
        assertion = jwt.encode(claims, key_data.get('private_key'), algorithm='RS256')
    except Exception as exc:
        raise GoogleWorkspaceDevicesError(f'Could not sign the request with this service account key: {exc}') from exc

    resp = requests.post(
        _TOKEN_URL,
        data={'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': assertion},
        timeout=8,
    )
    if not resp.ok:
        raise GoogleWorkspaceDevicesError(f'Google rejected this service account: {resp.text[:200]}')
    return resp.json()['access_token']


def test_credentials(config):
    token = _get_access_token(config)
    resp = requests.get(f'{_API_BASE}/customer/my_customer/devices/chromeos', headers={'Authorization': f'Bearer {token}'}, timeout=8)
    if not resp.ok:
        raise GoogleWorkspaceDevicesError(f'Google Workspace rejected this request: {resp.text[:200]}')
