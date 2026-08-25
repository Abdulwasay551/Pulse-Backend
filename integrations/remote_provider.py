"""Remote — BYOK via an API key generated directly from the org's own
Remote dashboard (a plain Bearer token). Connection-only for now, same
reasoning as deel_provider.py: Remote's API covers full EOR employment
management, but this app has no existing "EOR worker" concept to sync
that into yet."""

import requests

_API_BASE = 'https://gateway.remote.com/v1'


class RemoteError(Exception):
    pass


def test_credentials(config):
    """Used by the settings page's "Test" button."""
    resp = requests.get(f'{_API_BASE}/companies', headers={'Authorization': f"Bearer {config['api_token']}"}, timeout=8)
    if not resp.ok:
        raise RemoteError(f'Remote rejected this API key: {resp.text[:200]}')
