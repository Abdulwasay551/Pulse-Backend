from django.conf import settings
from django.db import models


class PayrollRun(models.Model):
    STATUS_CHOICES = [
        ('Reconciled', 'Reconciled'),
        ('Needs review', 'Needs review'),
        ('Processing', 'Processing'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payroll_runs')
    period = models.CharField(max_length=150)
    contractors = models.PositiveIntegerField(default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Processing')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.period
