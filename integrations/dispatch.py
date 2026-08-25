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


def _send_discord(config, message):
    resp = requests.post(config['webhook_url'], json={'content': message}, timeout=_TIMEOUT)
    resp.raise_for_status()


def _send_telegram(config, message):
    url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
    resp = requests.post(url, json={'chat_id': config['chat_id'], 'text': message}, timeout=_TIMEOUT)
    resp.raise_for_status()


_SENDERS = {
    'slack': lambda config, event, message, tone: _send_slack(config, message),
    'teams': lambda config, event, message, tone: _send_teams(config, message),
    'webhook': lambda config, event, message, tone: _send_webhook(config, event, message, tone),
    # Zapier's "Webhooks by Zapier" trigger is just a URL that accepts the
    # same JSON POST shape as the generic Custom Webhook — no separate
    # sender needed.
    'zapier': lambda config, event, message, tone: _send_webhook(config, event, message, tone),
    'twilio': lambda config, event, message, tone: _send_twilio_sms(config, message),
    'discord': lambda config, event, message, tone: _send_discord(config, message),
    'telegram': lambda config, event, message, tone: _send_telegram(config, message),
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


def _test_credentials_only(provider_error_cls, test_fn):
    """Adapts an action-integration's test_credentials(config) (Zoom/
    Checkr/Dropbox Sign — no send_message-shaped sender to reuse) into the
    same (config, event, message, tone) call signature _SENDERS uses, so
    test_connection below can treat every integration uniformly."""

    def _adapted(config, event, message, tone):
        try:
            test_fn(config)
        except provider_error_cls as exc:
            raise requests.exceptions.RequestException(str(exc)) from exc

    return _adapted


def _lazy_action_testers():
    """Imported lazily rather than at module load — this module is pulled
    in by core.activity.log_activity (every app's views import that very
    early), so keeping its own top-level imports minimal avoids adding
    those to Django's startup import chain for the common case (a
    notification-only integration) that never needs them."""
    from .checkr_provider import CheckrError, test_credentials as checkr_test
    from .deel_provider import DeelError, test_credentials as deel_test
    from .dropbox_sign_provider import DropboxSignError, test_credentials as dropbox_sign_test
    from .hackerrank_provider import HackerRankError, test_credentials as hackerrank_test
    from .remote_provider import RemoteError, test_credentials as remote_test
    from .surveymonkey_provider import SurveyMonkeyError, test_credentials as surveymonkey_test
    from .wise_provider import WiseError, test_credentials as wise_test
    from .zoom_provider import ZoomError, test_credentials as zoom_test

    return {
        'zoom': _test_credentials_only(ZoomError, zoom_test),
        'checkr': _test_credentials_only(CheckrError, checkr_test),
        'dropbox_sign': _test_credentials_only(DropboxSignError, dropbox_sign_test),
        'hackerrank': _test_credentials_only(HackerRankError, hackerrank_test),
        'wise': _test_credentials_only(WiseError, wise_test),
        'deel': _test_credentials_only(DeelError, deel_test),
        'remote': _test_credentials_only(RemoteError, remote_test),
        'surveymonkey': _test_credentials_only(SurveyMonkeyError, surveymonkey_test),
    }


def test_connection(connection):
    """Used by the "Test" button — unlike notify_all, this one surfaces its
    error, since the whole point is telling the user whether it worked."""
    meta = INTEGRATIONS.get(connection.integration_key)
    if not meta:
        raise IntegrationError('Unknown integration.')

    if connection.integration_key == 'smtp':
        # Needs the full connection (for .owner.email as the test
        # recipient), not just its config — doesn't fit the generic
        # (config, event, message, tone) shape every other sender uses.
        from .email_provider import EmailProviderError, test_credentials as smtp_test

        try:
            smtp_test(connection)
        except EmailProviderError as exc:
            raise IntegrationError(f'Could not send through this SMTP connection: {exc}') from exc
        return

    sender = _SENDERS.get(connection.integration_key) or _lazy_action_testers().get(connection.integration_key)
    if not sender:
        raise IntegrationError('Unknown integration.')
    try:
        sender(connection.get_config(), 'test', 'Pulse test notification — your connection is working.', 'primary')
    except requests.exceptions.RequestException as exc:
        raise IntegrationError(f'Could not reach {meta["label"]}: {exc}') from exc
