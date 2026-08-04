from .models import ActivityLog


def log_activity(owner_id: int, message: str, tone: str = 'neutral'):
    """`owner_id` is the tenant id (see core.permissions.owner_scope_id),
    not necessarily the acting user's own id — multiple logins can share
    one organization's activity feed."""
    ActivityLog.objects.create(owner_id=owner_id, message=message, tone=tone)
