"""Indeed — OAuth2 client_credentials (2-legged). Unlike LinkedIn Learning's
self-service admin console, Indeed's own docs describe getting a client_id/
client_secret as going through their Partner Console after becoming an
Indeed partner — flagged plainly in this integration's setup instructions
rather than glossed over, but not gated on here: whether the connecting
org already has (or can get) that access is their call to make, not
something this integration silently blocks on."""

import requests

_TOKEN_URL = 'https://apis.indeed.com/oauth/v2/tokens'


class IndeedError(Exception):
    pass


def test_credentials(config):
    resp = requests.post(
        _TOKEN_URL,
        headers={'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type': 'client_credentials',
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'scope': 'employer_access',
        },
        timeout=8,
    )
    if not resp.ok:
        raise IndeedError(f'Indeed rejected these credentials: {resp.text[:200]}')
