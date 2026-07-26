from datetime import date

from django.conf import settings
from django.db import models


class Employee(models.Model):
    """Employee Database / 360° Profiles (EVO-People > Employee Records) —
    the core entity every other People sub-module (attendance, engagement,
    workforce dashboard) will eventually hang off. Organizational Chart is
    derived from `manager` rather than a separate model."""

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('On Leave', 'On Leave'),
        ('Terminated', 'Terminated'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employees')
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=100, blank=True)
    manager = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='direct_reports'
    )
    hire_date = models.DateField(default=date.today)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    # If this person came through EVO-Recruit, link back to that record —
    # optional, since People also needs to support employees entered
    # directly (never having been a Candidate at all).
    source_candidate = models.ForeignKey(
        'recruit.Candidate', on_delete=models.SET_NULL, null=True, blank=True, related_name='employee_records'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class EmployeeDocument(models.Model):
    """Document management (EVO-People > Employee Records) — contracts,
    certifications, ID proofs, per employee."""

    DOC_TYPE_CHOICES = [
        ('Contract', 'Contract'),
        ('Certification', 'Certification'),
        ('ID Proof', 'ID proof'),
        ('Other', 'Other'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='Other')
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to='employee-documents/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.employee.name} — {self.title}'
