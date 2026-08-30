"""Xero — OAuth2 authorization_code only (confirmed live: identity.xero.com
returns a genuine invalid_client rejection). BYOK for the access token
itself, same simplification as Gusto/DocuSign: the org completes Xero's
own OAuth flow (via their own app registered at developer.xero.com — free
and self-serve for any developer, though the actual org's Xero data still
needs that org's own consent) however they manage that, and pastes the
resulting access token below. Connection-only — verifies via Xero's own
tenant-connections list, which needs no Xero-tenant-id header."""

import requests

_API_BASE = 'https://api.xero.com'


class XeroError(Exception):
    pass


def test_credentials(config):
    resp = requests.get(
        f'{_API_BASE}/connections', headers={'Authorization': f"Bearer {config['access_token']}"}, timeout=8
    )
    if not resp.ok:
        raise XeroError(f'Xero rejected this access token: {resp.text[:200]}')
