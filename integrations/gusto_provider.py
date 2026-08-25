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

_API_BASE = 'https://api.gusto.com'


class GustoError(Exception):
    pass


def test_credentials(config):
    resp = requests.get(
        f'{_API_BASE}/v1/me', headers={'Authorization': f"Bearer {config['access_token']}"}, timeout=8
    )
    if not resp.ok:
        raise GustoError(f'Gusto rejected this access token: {resp.text[:200]}')
