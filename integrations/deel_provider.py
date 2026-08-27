"""Deel — BYOK via an API key generated directly from the org's own Deel
Developer Center (a plain Bearer token, separate from Deel's OAuth-based
public-app marketplace flow). Read-only: this app has no existing "EOR
worker" concept to sync Deel's workforce data into, so rather than
building a one-way import, list_workers surfaces the org's live Deel
people list directly on the Payroll & Benefits dashboard instead."""

import requests

from .helpers import get_connection

_API_BASE = 'https://api.letsdeel.com/rest/v2'


class DeelError(Exception):
    pass


def _auth_headers(config):
    return {'Authorization': f"Bearer {config['api_token']}"}


def test_credentials(config):
    """Used by the settings page's "Test" button."""
    resp = requests.get(f'{_API_BASE}/people', headers=_auth_headers(config), timeout=8)
    if not resp.ok:
        raise DeelError(f'Deel rejected this API key: {resp.text[:200]}')


def list_workers(owner_id):
    """A real, live list of the connected Deel account's people — used by
    the Payroll & Benefits dashboard's Deel panel."""
    connection = get_connection(owner_id, 'deel')
    if not connection:
        raise DeelError('Deel is not connected. Connect it under Settings -> Integrations first.')
    config = connection.get_config()

    resp = requests.get(f'{_API_BASE}/people', headers=_auth_headers(config), timeout=10)
    if not resp.ok:
        raise DeelError(f'Deel could not list workers: {resp.text[:200]}')
    people = resp.json().get('data', [])
    return [
        {
            'id': p.get('id'),
            'name': p.get('full_name') or p.get('display_name'),
            'email': p.get('emails', [{}])[0].get('value') if p.get('emails') else None,
            'hiring_status': p.get('hiring_status'),
            'job_title': p.get('job_title'),
        }
        for p in people
    ]
