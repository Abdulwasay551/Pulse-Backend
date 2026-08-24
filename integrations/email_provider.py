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


def is_platform_email_configured() -> bool:
    """False for the console backend (prints to server logs, delivers
    nothing) — the honest signal that *no* email actually goes anywhere
    right now unless the org has its own SMTP connected."""
    return settings.EMAIL_BACKEND != 'django.core.mail.backends.console.EmailBackend'


def has_working_email(owner_id) -> bool:
    """Whether an email sent on this org's behalf will actually be
    delivered anywhere — either they've connected their own SMTP, or the
    platform default has been configured for real (not console-only)."""
    if is_platform_email_configured():
        return True
    return get_integration_connection(owner_id, 'smtp') is not None


def _build_backend(config, fail_silently):
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=config['host'],
        port=int(config.get('port') or 587),
        username=config['username'],
        password=config['password'],
        use_tls=True,
        fail_silently=fail_silently,
    )


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
        backend = _build_backend(config, fail_silently=False)
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
    """fail_silently=True (the default, for security-sensitive flows like
    password reset that must never reveal delivery state) swallows every
    failure exactly like Django's own send_mail does. Pass False (e.g. for
    an HR-initiated action like an employee invite, where the person
    triggering it is standing right there and can act on an error) to get
    a clean EmailProviderError instead of a raw SMTP/connection exception
    — see EmployeeInviteView for the "show it, don't hide it" caller."""
    connection = get_integration_connection(owner_id, 'smtp')
    try:
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
        backend = _build_backend(config, fail_silently)
        send_mail(
            subject=subject,
            message=message,
            from_email=config['from_email'],
            recipient_list=recipient_list,
            connection=backend,
            fail_silently=fail_silently,
        )
    except Exception as exc:
        if fail_silently:
            return
        raise EmailProviderError(str(exc)) from exc
