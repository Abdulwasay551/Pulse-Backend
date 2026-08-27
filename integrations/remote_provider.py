"""Remote — BYOK via an API key generated directly from the org's own
Remote dashboard (a plain Bearer token). Read-only, same reasoning as
deel_provider.py: this app has no existing "EOR worker" concept to sync
Remote's employment data into, so list_employments surfaces it directly
on the Payroll & Benefits dashboard instead."""

import requests

from .helpers import get_connection

_API_BASE = 'https://gateway.remote.com/v1'


class RemoteError(Exception):
    pass


def _auth_headers(config):
    return {'Authorization': f"Bearer {config['api_token']}"}


def test_credentials(config):
    """Used by the settings page's "Test" button."""
    resp = requests.get(f'{_API_BASE}/companies', headers=_auth_headers(config), timeout=8)
    if not resp.ok:
        raise RemoteError(f'Remote rejected this API key: {resp.text[:200]}')


def list_employments(owner_id):
    """A real, live list of the connected Remote account's employments —
    used by the Payroll & Benefits dashboard's Remote panel."""
    connection = get_connection(owner_id, 'remote')
    if not connection:
        raise RemoteError('Remote is not connected. Connect it under Settings -> Integrations first.')
    config = connection.get_config()

    resp = requests.get(f'{_API_BASE}/employments', headers=_auth_headers(config), timeout=10)
    if not resp.ok:
        raise RemoteError(f'Remote could not list employments: {resp.text[:200]}')
    employments = (resp.json().get('data') or {}).get('employments', [])
    return [
        {
            'id': e.get('id'),
            'name': e.get('full_name'),
            'email': e.get('personal_email') or e.get('email'),
            'status': e.get('status'),
            'job_title': e.get('job_title'),
            'country': (e.get('country') or {}).get('name'),
        }
        for e in employments
    ]
