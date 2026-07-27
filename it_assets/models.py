from datetime import date

from django.conf import settings
from django.db import models


class Asset(models.Model):
    """Asset Inventory Tracking — the core entity every other IT & Asset
    sub-module hangs off. Device Provisioning is `assigned_to`/`assigned_at`
    being set/cleared (tied to onboarding/offboarding conceptually, not a
    hard FK to either — an asset can be provisioned independent of a formal
    onboarding record). Warranty Tracking is a computed view over
    `warranty_expiry`, not a separate model."""

    CATEGORY_CHOICES = [
        ('Laptop', 'Laptop'),
        ('Monitor', 'Monitor'),
        ('Phone', 'Phone'),
        ('Tablet', 'Tablet'),
        ('Peripheral', 'Peripheral'),
        ('Other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('In Stock', 'In Stock'),
        ('Assigned', 'Assigned'),
        ('In Repair', 'In Repair'),
        ('Retired', 'Retired'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assets')
    asset_tag = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Laptop')
    serial_number = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='In Stock')
    assigned_to = models.ForeignKey(
        'people.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='assets'
    )
    assigned_at = models.DateField(null=True, blank=True)
    is_byod = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.asset_tag} — {self.name}'


class SupportTicket(models.Model):
    """IT Support Requests Management — device queries and repair requests,
    tracked as a support-desk workflow (not the incident/repair history
    itself, which is AssetIncident/"Device Tracker")."""

    CATEGORY_CHOICES = [
        ('Repair Request', 'Repair Request'),
        ('Device Query', 'Device Query'),
        ('Access Request', 'Access Request'),
        ('Other', 'Other'),
    ]
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='support_tickets')
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Device Query')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Open')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.subject


class AssetIncident(models.Model):
    """Device Tracker — issue history, repairs, and damage records for a
    specific asset."""

    INCIDENT_TYPE_CHOICES = [
        ('Damage', 'Damage'),
        ('Repair', 'Repair'),
        ('Loss', 'Loss'),
        ('Malfunction', 'Malfunction'),
        ('Other', 'Other'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='asset_incidents')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='incidents')
    employee = models.ForeignKey(
        'people.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='asset_incidents'
    )
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPE_CHOICES, default='Repair')
    description = models.TextField(blank=True)
    incident_date = models.DateField(default=date.today)
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-incident_date']

    def __str__(self):
        return f'{self.asset.asset_tag} — {self.incident_type}'


class BYODCompliance(models.Model):
    """BYOD Security Policy — tracks policy compliance per personal
    device (an Asset with `is_byod=True`)."""

    COMPLIANCE_STATUS_CHOICES = [
        ('Compliant', 'Compliant'),
        ('Non-Compliant', 'Non-Compliant'),
        ('Pending Review', 'Pending Review'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='byod_checks')
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='byod_checks')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='byod_checks')
    encryption_enabled = models.BooleanField(default=False)
    antivirus_installed = models.BooleanField(default=False)
    passcode_enabled = models.BooleanField(default=False)
    compliance_status = models.CharField(max_length=20, choices=COMPLIANCE_STATUS_CHOICES, default='Pending Review')
    last_checked = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.employee.name} — {self.asset.asset_tag}'
