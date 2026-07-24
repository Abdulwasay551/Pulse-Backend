from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone


class Client(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Prospect', 'Prospect'),
        ('At risk', 'At risk'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='clients')
    name = models.CharField(max_length=150)
    industry = models.CharField(max_length=100, blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Prospect')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Requisition(models.Model):
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Interviewing', 'Interviewing'),
        ('Offer stage', 'Offer stage'),
        ('On hold', 'On hold'),
        ('Filled', 'Filled'),
    ]
    # Requisitions stop counting toward a client's "open roles" once they
    # land in one of these — everything else is still actively being worked.
    OPEN_STATUSES = ['Open', 'Interviewing', 'Offer stage']

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='requisitions')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='requisitions')
    title = models.CharField(max_length=150)
    recruiter = models.CharField(max_length=150, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    posted_at = models.DateField(default=date.today)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Candidate(models.Model):
    STAGE_CHOICES = [
        ('Sourced', 'Sourced'),
        ('Interview', 'Interview'),
        ('Offer', 'Offer'),
        ('Placed', 'Placed'),
        ('Rejected', 'Rejected'),
    ]
    SOURCE_CHOICES = [
        ('LinkedIn', 'LinkedIn'),
        ('Referral', 'Referral'),
        ('Job Board', 'Job Board'),
        ('Sourced', 'Sourced'),
        ('Other', 'Other'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='candidates')
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150)
    client = models.ForeignKey(
        Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidates'
    )
    requisition = models.ForeignKey(
        Requisition, on_delete=models.SET_NULL, null=True, blank=True, related_name='candidates'
    )
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='Sourced')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='Sourced')
    applied_at = models.DateField(default=date.today)
    # Set automatically the moment stage becomes "Placed" (see save()) — this
    # is what the placements-per-month trend is computed from, independent of
    # whatever applied_at was.
    placed_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.stage == 'Placed' and not self.placed_at:
            self.placed_at = timezone.now().date()
        elif self.stage != 'Placed':
            self.placed_at = None
        super().save(*args, **kwargs)


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


class ActivityLog(models.Model):
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
