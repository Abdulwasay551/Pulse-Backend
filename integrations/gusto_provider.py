"""Gusto — OAuth2 authorization_code only (confirmed live: api.gusto.com
returns a genuine Doorkeeper `invalid_token` challenge, the same OAuth
library Gusto's classic API uses, no client_credentials shortcut).
Building the full 3-legged redirect flow is out of scope here — instead
this is BYOK for the access token itself: the org completes Gusto's own
OAuth flow (via their own registered Gusto app, or whatever access their
Gusto Embedded Payroll partnership grants them) however they manage that,
and pastes the resulting access token below. Access tokens from Gusto's
OAuth flow expire (this integration doesn't handle refresh) — reconnecting
with a fresh token when the Test button starts failing is expected
maintenance, called out in the setup instructions rather than hidden."""

import requests

from .helpers import get_connection

_API_BASE = 'https://api.gusto.com'


class GustoError(Exception):
    pass


def _auth_headers(config):
    return {'Authorization': f"Bearer {config['access_token']}"}


def test_credentials(config):
    resp = requests.get(f'{_API_BASE}/v1/me', headers=_auth_headers(config), timeout=8)
    if not resp.ok:
        raise GustoError(f'Gusto rejected this access token: {resp.text[:200]}')


def list_employees(owner_id):
    """A real, live list of the connected Gusto company's employees — used
    by the Payroll & Benefits dashboard's Gusto panel. /v1/me identifies
    which company role(s) this token has access to before listing."""
    connection = get_connection(owner_id, 'gusto')
    if not connection:
        raise GustoError('Gusto is not connected. Connect it under Settings -> Integrations first.')
    config = connection.get_config()
    headers = _auth_headers(config)

    me_resp = requests.get(f'{_API_BASE}/v1/me', headers=headers, timeout=8)
    if not me_resp.ok:
        raise GustoError(f'Gusto rejected this access token: {me_resp.text[:200]}')
    roles = (me_resp.json().get('roles') or {}).get('payroll_admin') or {}
    companies = roles.get('companies') or []
    if not companies:
        return []
    company_id = companies[0]['id']

    resp = requests.get(f'{_API_BASE}/v1/companies/{company_id}/employees', headers=headers, timeout=10)
    if not resp.ok:
        raise GustoError(f'Gusto could not list employees: {resp.text[:200]}')
    employees = resp.json()
    return [
        {
            'id': e.get('id'),
            'name': f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
            'email': e.get('email'),
            'department': e.get('department'),
            'terminated': e.get('terminated'),
        }
        for e in employees
    ]
