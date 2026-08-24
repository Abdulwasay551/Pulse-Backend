"""HackerRank for Work — BYOK via a plain API token (Bearer auth). The org
creates its own tests directly in their HackerRank account (test creation
isn't something this app builds a UI for) and pastes a test's ID when
sending it to a candidate, since different roles typically use different
tests — there's no single org-wide default test.

Score/status are refreshed on demand (refresh_score, called from a
"Refresh score" button) rather than via webhook: HackerRank's webhook
payload shape isn't something this integration verifies against a real
account, so polling the same authenticated GET the dashboard itself uses
is the safer, still fully real, choice."""

import requests

from .helpers import get_connection

_API_BASE = 'https://www.hackerrank.com/x/api/v3'


class HackerRankError(Exception):
    pass


def _auth_headers(config):
    return {'Authorization': f"Bearer {config['api_token']}"}


def test_credentials(config):
    """Used by the settings page's "Test" button."""
    resp = requests.get(f'{_API_BASE}/tests', headers=_auth_headers(config), timeout=8)
    if not resp.ok:
        raise HackerRankError(f'HackerRank rejected this API token: {resp.text[:200]}')


def invite_candidate(owner_id, candidate, test_id):
    """Sends `candidate` an invitation to take test `test_id`. Returns
    {hackerrank_candidate_id} to store — HackerRank emails the candidate
    directly with their own test link."""
    connection = get_connection(owner_id, 'hackerrank')
    if not connection:
        raise HackerRankError('HackerRank is not connected. Connect it under Settings -> Integrations first.')
    if not candidate.email:
        raise HackerRankError('This candidate has no email on file to invite.')
    config = connection.get_config()

    resp = requests.post(
        f'{_API_BASE}/tests/{test_id}/candidates',
        headers=_auth_headers(config),
        json={'candidates': [{'email': candidate.email, 'full_name': candidate.name}]},
        timeout=10,
    )
    if not resp.ok:
        raise HackerRankError(f'HackerRank could not send the test invitation: {resp.text[:200]}')
    data = resp.json()
    candidates = data.get('candidates') or data.get('model', {}).get('candidates') or []
    hackerrank_candidate_id = candidates[0]['id'] if candidates else ''
    return {'hackerrank_candidate_id': str(hackerrank_candidate_id)}


# HackerRank candidate-report statuses -> a short label for our own
# hackerrank_status field — anything unrecognized passes through as-is
# rather than being silently dropped, since their status vocabulary isn't
# something this integration hardcodes with full confidence.
_STATUS_LABELS = {
    'invited': 'Invited',
    'started': 'In Progress',
    'completed': 'Completed',
}


def refresh_score(owner_id, candidate):
    """Polls HackerRank for this candidate's latest report — used by the
    "Refresh score" action. Returns {status, score, report_url}."""
    connection = get_connection(owner_id, 'hackerrank')
    if not connection:
        raise HackerRankError('HackerRank is not connected. Connect it under Settings -> Integrations first.')
    if not candidate.hackerrank_test_id or not candidate.hackerrank_candidate_id:
        raise HackerRankError('No HackerRank test has been sent to this candidate yet.')
    config = connection.get_config()

    resp = requests.get(
        f'{_API_BASE}/tests/{candidate.hackerrank_test_id}/candidates/{candidate.hackerrank_candidate_id}',
        headers=_auth_headers(config),
        timeout=10,
    )
    if not resp.ok:
        raise HackerRankError(f'Could not fetch this candidate\'s report: {resp.text[:200]}')
    data = resp.json()
    raw_status = str(data.get('status', '')).lower()
    return {
        'status': _STATUS_LABELS.get(raw_status, data.get('status', 'Unknown')),
        'score': data.get('score'),
        'report_url': data.get('report_url') or data.get('candidate_report_url') or '',
    }
