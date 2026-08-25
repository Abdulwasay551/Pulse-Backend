"""Deel — BYOK via an API key generated directly from the org's own Deel
Developer Center (a plain Bearer token, separate from Deel's OAuth-based
public-app marketplace flow). Connection-only for now: Deel's own API
covers full EOR/contractor payroll management, but this app has no
existing "EOR worker" concept to sync that into — see the settings
catalog description for the deliberately narrow v1 scope here."""

import requests

_API_BASE = 'https://api.letsdeel.com/rest/v2'


class DeelError(Exception):
    pass


def test_credentials(config):
    """Used by the settings page's "Test" button."""
    resp = requests.get(f'{_API_BASE}/people', headers={'Authorization': f"Bearer {config['api_token']}"}, timeout=8)
    if not resp.ok:
        raise DeelError(f'Deel rejected this API key: {resp.text[:200]}')
