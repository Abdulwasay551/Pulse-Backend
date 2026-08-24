"""Checkr — BYOK via a plain API key (Basic Auth, key as username, blank
password, same convention Checkr's own docs use). Real flow: create a
Checkr Candidate, then an Invitation against it (Checkr emails the
candidate to fill in consent/SSN/etc. themselves) — a Report is created
asynchronously once they complete that, and its status changes flow back
via webhook (see verify_webhook_signature + views.CheckrWebhookView)."""

import hashlib
import hmac

import requests

from .helpers import get_connection

_API_BASE = 'https://api.checkr.com/v1'


class CheckrError(Exception):
    pass


def _auth(config):
    return (config['api_key'], '')


def test_credentials(config):
    """Used by the settings page's "Test" button — a cheap authenticated
    GET, no candidate/invitation created."""
    resp = requests.get(f'{_API_BASE}/account', auth=_auth(config), timeout=8)
    if not resp.ok:
        raise CheckrError(f'Checkr rejected this API key: {resp.text[:200]}')


def initiate_check(owner_id, candidate, package='basic_plus'):
    """candidate is a people-side recruit.models.Candidate instance.
    Returns {checkr_candidate_id, checkr_report_id} — report_id is actually
    the *invitation* id at this point (Checkr's report doesn't exist until
    the candidate completes their part); the webhook matches on whichever
    id it receives, see CheckrWebhookView."""
    connection = get_connection(owner_id, 'checkr')
    if not connection:
        raise CheckrError('Checkr is not connected. Connect it under Settings -> Integrations first.')
    config = connection.get_config()

    name_parts = candidate.name.split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    resp = requests.post(
        f'{_API_BASE}/candidates',
        auth=_auth(config),
        json={'email': candidate.email, 'first_name': first_name, 'last_name': last_name},
        timeout=8,
    )
    if not resp.ok:
        raise CheckrError(f'Checkr could not create a candidate: {resp.text[:200]}')
    checkr_candidate_id = resp.json()['id']

    resp = requests.post(
        f'{_API_BASE}/invitations',
        auth=_auth(config),
        json={'candidate_id': checkr_candidate_id, 'package': package},
        timeout=8,
    )
    if not resp.ok:
        raise CheckrError(f'Checkr could not send the invitation: {resp.text[:200]}')
    invitation_id = resp.json()['id']

    return {'checkr_candidate_id': checkr_candidate_id, 'checkr_report_id': invitation_id}


# Checkr report statuses -> this app's own BackgroundCheck.STATUS_CHOICES.
_STATUS_MAP = {
    'pending': 'Pending',
    'clear': 'Cleared',
    'consider': 'Flagged',
    'suspended': 'Flagged',
    'disputed': 'Flagged',
}


def map_report_status(checkr_status: str) -> str:
    return _STATUS_MAP.get(checkr_status, 'In Progress')


def verify_webhook_signature(config, payload_body: bytes, signature_header: str) -> bool:
    secret = config.get('webhook_secret')
    if not secret:
        # No secret configured — the org skipped that optional setup step;
        # accept the webhook rather than silently dropping every status
        # update (same trade-off Dropbox Sign's receiver below makes).
        return True
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or '')
