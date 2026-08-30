"""Sage Business Cloud — OAuth2 authorization_code only (confirmed live:
api.accounting.sage.com returns a genuine 401 AccessDeniedException). BYOK
for the access token, same simplification pattern as Gusto/DocuSign/Xero/
QuickBooks: the org completes Sage's own OAuth flow (via their own app
registered at Sage Developer) however they manage that."""

import requests

_API_BASE = 'https://api.accounting.sage.com/v3.1'


class SageError(Exception):
    pass


def test_credentials(config):
    resp = requests.get(
        f'{_API_BASE}/businesses', headers={'Authorization': f"Bearer {config['access_token']}"}, timeout=8
    )
    if not resp.ok:
        raise SageError(f'Sage rejected this access token: {resp.text[:200]}')
