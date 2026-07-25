from .models import ActivityLog


def log_activity(user, message: str, tone: str = 'neutral'):
    ActivityLog.objects.create(owner=user, message=message, tone=tone)
