import uuid
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
    # Employee Self-Service is a public, no-login "view my own profile" page
    # (frontend: /employee-portal/[token]) — same reasoning as EVO-Recruit's
    # Candidate Portal: the employee isn't an authenticated user of this
    # system, so a stable secret link gives real self-service value without
    # a second auth system.
    portal_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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


class AttendanceRecord(models.Model):
    """Clock-in/Clock-out Tracking + Overtime Tracking (EVO-People >
    Attendance Management) — one row per employee per day. Overtime
    tracking is a filtered view over this (hours worked past a threshold),
    not a separate model."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance_records')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=date.today)
    clock_in = models.TimeField(null=True, blank=True)
    clock_out = models.TimeField(null=True, blank=True)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.employee.name} — {self.date}'


class Shift(models.Model):
    """Shift Scheduling per Department (EVO-People > Attendance
    Management)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shifts')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='shifts')
    date = models.DateField(default=date.today)
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'start_time']

    def __str__(self):
        return f'{self.employee.name} — {self.date} {self.start_time}–{self.end_time}'


class LeaveRequest(models.Model):
    """Leave & Absence Management (EVO-People > Attendance Management) —
    requests, approvals, balances (balances are derived by counting
    Approved days, not stored separately)."""

    TYPE_CHOICES = [
        ('Vacation', 'Vacation'),
        ('Sick', 'Sick'),
        ('Personal', 'Personal'),
        ('Unpaid', 'Unpaid'),
        ('Other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_requests')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='Vacation')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.employee.name} — {self.leave_type} ({self.start_date} to {self.end_date})'


class Survey(models.Model):
    """Surveys + Pulse Checks (EVO-People > Employee Engagement) — the same
    model with a `kind` flag, since a pulse check is just a lighter-weight
    survey, not a structurally different thing."""

    KIND_CHOICES = [
        ('Survey', 'Survey'),
        ('Pulse Check', 'Pulse check'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='surveys')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='Survey')
    title = models.CharField(max_length=200)
    question = models.TextField(help_text='The question employees are asked to respond to.')
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class SurveyResponse(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='survey_responses')
    rating = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Optional 1–5 sentiment rating.')
    response_text = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.employee.name} → {self.survey.title}'


class Recognition(models.Model):
    """Recognition Programs (EVO-People > Employee Engagement) — a public
    kudos/shoutout board."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recognitions')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='recognitions')
    given_by = models.CharField(max_length=150, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Recognition for {self.employee.name}'


class PromotionRequest(models.Model):
    """Promotion & Transfer Workflows within Department (EVO-People >
    Employee Engagement)."""

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='promotion_requests')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='promotion_requests')
    from_title = models.CharField(max_length=150, blank=True)
    to_title = models.CharField(max_length=150, blank=True)
    from_department = models.CharField(max_length=100, blank=True)
    to_department = models.CharField(max_length=100, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee.name}: {self.from_title} → {self.to_title}'
