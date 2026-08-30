"""QuickBooks (Intuit) — OAuth2 authorization_code only (confirmed live:
oauth.platform.intuit.com returns a genuine 401 Basic-realm challenge).
BYOK for the access token plus the Realm ID (QuickBooks' company
identifier, required in every API call's URL path and not resolvable
generically the way Xero's tenant is) — same simplification pattern as
Gusto/DocuSign/Xero: the org completes Intuit's own OAuth flow (via
their own free app at developer.intuit.com) however they manage that."""

import requests

_API_BASE = 'https://quickbooks.api.intuit.com'


class QuickBooksError(Exception):
    pass


def test_credentials(config):
    realm_id = config['realm_id']
    resp = requests.get(
        f'{_API_BASE}/v3/company/{realm_id}/companyinfo/{realm_id}',
        headers={'Authorization': f"Bearer {config['access_token']}", 'Accept': 'application/json'},
        timeout=8,
    )
    if not resp.ok:
        raise QuickBooksError(f'QuickBooks rejected this token/Realm ID: {resp.text[:200]}')
