"""LinkedIn Learning — BYOK via a Client Id/Secret pair an org's own
LinkedIn Learning admin generates directly from their own Admin console
(Admin -> Access content and reports via API -> Add application ->
Report scope), confirmed via LinkedIn's own docs to be self-service —
no LinkedIn approval of Pulse itself is required, unlike Indeed's
partner-gated model. OAuth2 client_credentials, exchanged fresh on
every use rather than cached — this is a low-volume connection-
verification integration, not a high-throughput one."""

import requests

_TOKEN_URL = 'https://www.linkedin.com/oauth/v2/accessToken'


class LinkedInLearningError(Exception):
    pass


def test_credentials(config):
    """The client_credentials exchange itself is the real, meaningful
    test — a bad client_id/secret gets a genuine rejection straight from
    LinkedIn's own OAuth server."""
    resp = requests.post(
        _TOKEN_URL,
        data={
            'grant_type': 'client_credentials',
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
        },
        timeout=8,
    )
    if not resp.ok:
        raise LinkedInLearningError(f'LinkedIn rejected these credentials: {resp.text[:200]}')
