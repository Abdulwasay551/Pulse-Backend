"""Outbound senders, one per integration key, plus notify_all — the single
call core.activity.log_activity makes so every existing (and future)
log_activity(...) call site in the app automatically becomes notifiable
without ever being touched itself. Every sender is best-effort: a slow or
failing third party must never break the feature that logged the
activity, so every call is short-timeout and swallows its own errors,
surfacing failures only through the explicit "Test connection" action
(test_connection below), never silently inside a real request."""

import requests

from .catalog import INTEGRATIONS

_TIMEOUT = 4


class IntegrationError(Exception):
    pass


def _send_slack(config, message):
    resp = requests.post(config['webhook_url'], json={'text': message}, timeout=_TIMEOUT)
    resp.raise_for_status()


def _send_teams(config, message):
    resp = requests.post(config['webhook_url'], json={'text': message}, timeout=_TIMEOUT)
    resp.raise_for_status()


def _send_webhook(config, event, message, tone):
    resp = requests.post(
        config['webhook_url'], json={'event': event, 'message': message, 'tone': tone}, timeout=_TIMEOUT
    )
    resp.raise_for_status()


def _send_twilio_sms(config, message):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config['account_sid']}/Messages.json"
    resp = requests.post(
        url,
        data={'From': config['from_number'], 'To': config['to_number'], 'Body': message[:1500]},
        auth=(config['account_sid'], config['auth_token']),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()


_SENDERS = {
    'slack': lambda config, event, message, tone: _send_slack(config, message),
    'teams': lambda config, event, message, tone: _send_teams(config, message),
    'webhook': lambda config, event, message, tone: _send_webhook(config, event, message, tone),
    'twilio': lambda config, event, message, tone: _send_twilio_sms(config, message),
}


def notify_all(owner_id, message, tone, event='activity'):
    """Fires `message` to every enabled, tone-matching connection for this
    owner. Imports IntegrationConnection lazily to avoid a hard import
    cycle risk (core.activity is imported very early via every app's
    views); failures are swallowed per-connection so one broken webhook
    never blocks another or the caller."""
    from .models import IntegrationConnection

    connections = IntegrationConnection.objects.filter(owner_id=owner_id, is_enabled=True)
    for conn in connections:
        meta = INTEGRATIONS.get(conn.integration_key)
        sender = _SENDERS.get(conn.integration_key)
        if not meta or not sender or tone not in meta.get('notify_tones', set()):
            continue
        try:
            sender(conn.get_config(), event, message, tone)
        except Exception:
            continue


def test_connection(connection):
    """Used by the "Test" button — unlike notify_all, this one surfaces its
    error, since the whole point is telling the user whether it worked."""
    meta = INTEGRATIONS.get(connection.integration_key)
    sender = _SENDERS.get(connection.integration_key)
    if not meta or not sender:
        raise IntegrationError('Unknown integration.')
    try:
        sender(connection.get_config(), 'test', 'Pulse test notification — your connection is working.', 'primary')
    except requests.exceptions.RequestException as exc:
        raise IntegrationError(f'Could not reach {meta["label"]}: {exc}') from exc
