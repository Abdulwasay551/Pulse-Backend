"""SurveyMonkey — BYOK via a Private App access token, generated directly
from the org's own SurveyMonkey account (Account -> API -> Add a New App ->
Private App). This is SurveyMonkey's own self-serve path for connecting a
single account to an internal tool; it doesn't require SurveyMonkey's
review or a partner relationship, unlike a Public/OAuth app listed in
their marketplace. Deliberately read-only — this pulls the org's existing
survey list and response counts for display alongside Pulse's own native
Surveys feature, it never creates or edits a SurveyMonkey survey."""

import requests

from .helpers import get_connection

_API_BASE = 'https://api.surveymonkey.com/v3'


class SurveyMonkeyError(Exception):
    pass


def _auth_headers(config):
    return {'Authorization': f"Bearer {config['api_token']}"}


def test_credentials(config):
    resp = requests.get(f'{_API_BASE}/users/me', headers=_auth_headers(config), timeout=8)
    if not resp.ok:
        raise SurveyMonkeyError(f'SurveyMonkey rejected this access token: {resp.text[:200]}')


def list_surveys(owner_id):
    """Real, live list of the connected account's surveys plus each one's
    response count — used by the Surveys page's "Sync from SurveyMonkey"
    panel. Nothing is persisted; this is fetched fresh each time."""
    connection = get_connection(owner_id, 'surveymonkey')
    if not connection:
        raise SurveyMonkeyError('SurveyMonkey is not connected. Connect it under Settings -> Integrations first.')
    config = connection.get_config()
    headers = _auth_headers(config)

    resp = requests.get(f'{_API_BASE}/surveys', headers=headers, params={'per_page': 20}, timeout=10)
    if not resp.ok:
        raise SurveyMonkeyError(f'SurveyMonkey could not list surveys: {resp.text[:200]}')
    surveys = resp.json().get('data', [])

    results = []
    for s in surveys:
        detail_resp = requests.get(f"{_API_BASE}/surveys/{s['id']}", headers=headers, timeout=10)
        response_count = None
        date_modified = s.get('date_modified')
        if detail_resp.ok:
            detail = detail_resp.json()
            response_count = detail.get('response_count')
            date_modified = detail.get('date_modified', date_modified)
        results.append({
            'id': s.get('id'),
            'title': s.get('title') or s.get('nickname'),
            'response_count': response_count,
            'date_modified': date_modified,
            'href': s.get('href'),
        })
    return results
