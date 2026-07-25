from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """A cross-module activity feed entry — any module app can write to this
    (see core.activity.log_activity) so a user's dashboard can show one
    unified "recent activity" list regardless of which module the action
    happened in."""

    TONE_CHOICES = [
        ('primary', 'primary'),
        ('amber', 'amber'),
        ('maroon', 'maroon'),
        ('neutral', 'neutral'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activity_log')
    message = models.CharField(max_length=255)
    tone = models.CharField(max_length=10, choices=TONE_CHOICES, default='neutral')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.message


class DemoRequest(models.Model):
    """A submission of the public "Book a Demo" form."""

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    contact_number = models.CharField(max_length=30)
    business_name = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.business_name})'
