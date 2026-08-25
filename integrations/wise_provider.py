"""Wise — BYOK via a personal/business API token (Bearer auth), generated
directly from the org's own Wise account settings. Deliberately read-only
in this integration: quotes and account verification never move money —
see the module's own docstring in the settings catalog for why actually
executing a transfer isn't built here (a much bigger, higher-stakes
feature than the rest of this app's integrations, and worth its own
careful design pass rather than shipping alongside a batch of
notification/scheduling connections)."""

import requests

from .helpers import get_connection

_API_BASE = 'https://api.wise.com'


class WiseError(Exception):
    pass


def _auth_headers(config):
    return {'Authorization': f"Bearer {config['api_token']}"}


def test_credentials(config):
    """Used by the settings page's "Test" button — lists the account's
    profiles, the same read any real usage starts with."""
    resp = requests.get(f'{_API_BASE}/v2/profiles', headers=_auth_headers(config), timeout=8)
    if not resp.ok:
        raise WiseError(f'Wise rejected this API token: {resp.text[:200]}')


def get_quote(owner_id, source_currency, target_currency, source_amount):
    """A real, live Wise quote — exchange rate and fee for a hypothetical
    transfer, no money moved and nothing persisted. Used by the Multi-
    Currency page's "Get Wise quote" action."""
    connection = get_connection(owner_id, 'wise')
    if not connection:
        raise WiseError('Wise is not connected. Connect it under Settings -> Integrations first.')
    config = connection.get_config()

    resp = requests.post(
        f'{_API_BASE}/v3/quotes',
        headers=_auth_headers(config),
        json={
            'sourceCurrency': source_currency.upper(),
            'targetCurrency': target_currency.upper(),
            'sourceAmount': float(source_amount),
        },
        timeout=10,
    )
    if not resp.ok:
        raise WiseError(f'Wise could not generate a quote: {resp.text[:200]}')
    data = resp.json()
    payment_option = (data.get('paymentOptions') or [{}])[0]
    return {
        'source_amount': data.get('sourceAmount'),
        'target_amount': payment_option.get('targetAmount') or data.get('targetAmount'),
        'rate': data.get('rate'),
        'fee': payment_option.get('fee', {}).get('total'),
    }
