"""Per-org SMTP — if an org has connected its own mail provider, every
transactional email sent *to or on behalf of* that org (password resets,
employee invites) goes out through it, from their own address, instead of
Pulse's shared platform default. No connection = falls straight through
to Django's normal send_mail (whatever EMAIL_BACKEND is configured
platform-wide — console in dev, or a future platform-default SMTP)."""

from django.conf import settings
from django.core.mail import get_connection, send_mail

from .helpers import get_connection as get_integration_connection


class EmailProviderError(Exception):
    pass


def test_credentials(connection):
    """Used by the settings page's "Test" button — sends a real test email
    to the connecting admin's own address (there's no other natural
    recipient for an SMTP connection's test, unlike Slack/webhook where
    the destination is already baked into the config)."""
    to_email = connection.owner.email
    if not to_email:
        raise EmailProviderError('Your account has no email on file to send a test to.')
    config = connection.get_config()
    try:
        backend = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=config['host'],
            port=int(config.get('port') or 587),
            username=config['username'],
            password=config['password'],
            use_tls=True,
            fail_silently=False,
        )
        send_mail(
            subject='Pulse test email',
            message='This is a test email from Pulse — your SMTP connection is working.',
            from_email=config['from_email'],
            recipient_list=[to_email],
            connection=backend,
            fail_silently=False,
        )
    except Exception as exc:
        raise EmailProviderError(str(exc)) from exc


def send_org_email(owner_id, subject, message, recipient_list, fail_silently=True):
    connection = get_integration_connection(owner_id, 'smtp')
    if not connection:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=fail_silently,
        )
        return

    config = connection.get_config()
    backend = get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=config['host'],
        port=int(config.get('port') or 587),
        username=config['username'],
        password=config['password'],
        use_tls=True,
        fail_silently=fail_silently,
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=config['from_email'],
        recipient_list=recipient_list,
        connection=backend,
        fail_silently=fail_silently,
    )
