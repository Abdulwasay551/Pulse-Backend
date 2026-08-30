"""DocuSign — OAuth-only (no static API key, unlike Dropbox Sign's classic
API key model), confirmed live via a genuine `invalid_request` rejection
at DocuSign's own token endpoint. BYOK for the access token itself: the
org completes DocuSign's own OAuth flow (JWT Grant or Authorization Code,
via their own free Developer sandbox account — self-serve, no DocuSign
approval of Pulse needed) however they manage that, and pastes the
resulting access token below, same simplification as the Gusto
integration. Connection-only for now — a distinct, brand-recognized
alternative to the Dropbox Sign integration already built, not a
replacement for it."""

import requests

_ENVIRONMENTS = {
    'demo': 'https://account-d.docusign.com',
    'production': 'https://account.docusign.com',
}


class DocuSignError(Exception):
    pass


def test_credentials(config):
    env = (config.get('environment') or 'demo').strip().lower()
    base = _ENVIRONMENTS.get(env)
    if not base:
        raise DocuSignError('Environment must be "demo" or "production".')
    resp = requests.get(
        f'{base}/oauth/userinfo', headers={'Authorization': f"Bearer {config['access_token']}"}, timeout=8
    )
    if not resp.ok:
        raise DocuSignError(f'DocuSign rejected this access token: {resp.text[:200]}')
