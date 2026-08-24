"""Zoom Server-to-Server OAuth — each org creates its own Zoom app (see
catalog.py's setup instructions) and pastes the 3 credentials; no browser
OAuth consent flow, no app registration on Pulse's own side."""

import requests

from .helpers import get_connection


class ZoomError(Exception):
    pass


def _get_access_token(config):
    resp = requests.post(
        'https://zoom.us/oauth/token',
        params={'grant_type': 'account_credentials', 'account_id': config['account_id']},
        auth=(config['client_id'], config['client_secret']),
        timeout=8,
    )
    if not resp.ok:
        raise ZoomError(f'Zoom rejected these credentials: {resp.text[:200]}')
    return resp.json()['access_token']


def test_credentials(config):
    """Used by the settings page's "Test" button — just confirms the
    account/client id/secret combination actually mints a token, without
    creating a real meeting."""
    _get_access_token(config)


def create_meeting(owner_id, topic, start_time=None, duration_minutes=30):
    """Creates an instant meeting (no start_time) or a scheduled one (ISO
    8601 start_time, e.g. '2026-09-01T14:00:00Z'). Returns the join URL —
    nothing is persisted on this side; the caller (a candidate's interview
    action) hands it straight back to the user to share."""
    connection = get_connection(owner_id, 'zoom')
    if not connection:
        raise ZoomError('Zoom is not connected. Connect it under Settings -> Integrations first.')

    config = connection.get_config()
    token = _get_access_token(config)
    payload = {
        'topic': topic,
        'type': 2 if start_time else 1,
        'duration': duration_minutes,
        'settings': {'join_before_host': True, 'waiting_room': False},
    }
    if start_time:
        payload['start_time'] = start_time

    resp = requests.post(
        'https://api.zoom.us/v2/users/me/meetings',
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=8,
    )
    if not resp.ok:
        raise ZoomError(f'Zoom could not create the meeting: {resp.text[:200]}')
    data = resp.json()
    return {'join_url': data['join_url'], 'start_url': data.get('start_url'), 'meeting_id': data['id']}
