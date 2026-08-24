from .models import ActivityLog


def log_activity(owner_id: int, message: str, tone: str = 'neutral'):
    """`owner_id` is the tenant id (see core.permissions.owner_scope_id),
    not necessarily the acting user's own id — multiple logins can share
    one organization's activity feed.

    Also the single place every connected third-party integration
    (Slack/Teams/webhook/SMS) gets notified from — every existing and
    future log_activity(...) call site across every module becomes
    notifiable for free, with no per-feature wiring, the moment an org
    connects one. See integrations.dispatch.notify_all for the tone-based
    filtering (routine 'neutral' activity never fires a notification)."""
    ActivityLog.objects.create(owner_id=owner_id, message=message, tone=tone)

    from integrations.dispatch import notify_all

    notify_all(owner_id, message, tone)
