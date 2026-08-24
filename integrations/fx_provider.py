"""Live foreign-exchange rates — unlike every other provider in this
package, this one needs no account or API key at all: Frankfurter (ECB
reference rates, ecb.europa.eu via frankfurter.dev) is a genuinely free,
no-auth-required public API, so "connect your own FX provider" would just
be friction for zero benefit. One function, called directly from
ExchangeRateViewSet.sync_live_rates — no IntegrationConnection involved."""

from decimal import Decimal

import requests


class FxProviderError(Exception):
    pass


def fetch_live_rates(currencies: list[str]) -> dict[str, Decimal]:
    """Returns {currency_code: rate_to_usd} — USD per 1 unit of that
    currency, matching ExchangeRate.rate_to_usd's own convention (the
    inverse of Frankfurter's own from-USD rates)."""
    codes = [c for c in currencies if c and c.upper() != 'USD']
    if not codes:
        return {}
    resp = requests.get(
        'https://api.frankfurter.dev/v1/latest',
        params={'base': 'USD', 'symbols': ','.join(codes)},
        timeout=8,
    )
    if not resp.ok:
        raise FxProviderError(f'Could not fetch live rates: {resp.text[:200]}')
    rates = resp.json().get('rates', {})
    return {code: (Decimal(1) / Decimal(str(rate))) for code, rate in rates.items() if rate}
