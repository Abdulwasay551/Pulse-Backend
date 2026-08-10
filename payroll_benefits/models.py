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
    # Multi-Currency Support — which currency `amount` is denominated in.
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Processing')
    # Payroll Audit & Reconciliation Reports — flagged/annotated here rather
    # than as a separate model, same reasoning as Offboarding.rehire_notes.
    discrepancy_flagged = models.BooleanField(default=False)
    audit_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.period


class ExchangeRate(models.Model):
    """Multi-Currency Support — HR/Finance Admin-maintained conversion
    rates (no live FX API is provisioned for this project, so "daily FX
    feed" becomes "manually refreshed, with `updated_at` showing how
    stale it is" — the practical version of "rate locked on a monthly
    basis"). `rate_to_usd` is USD per 1 unit of `currency`."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exchange_rates')
    currency = models.CharField(max_length=3)
    rate_to_usd = models.DecimalField(max_digits=12, decimal_places=6, default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['currency']
        unique_together = ['owner', 'currency']

    def __str__(self):
        return f'{self.currency} = {self.rate_to_usd} USD'


class TaxProfile(models.Model):
    """Multi-Country Tax Compliance — one per employee, tracking which
    jurisdiction's payroll taxes they're filed under and whether that
    filing is currently in good standing."""

    FILING_STATUS_CHOICES = [
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Head of Household', 'Head of Household'),
        ('Not Applicable', 'Not Applicable'),
    ]
    COMPLIANCE_STATUS_CHOICES = [
        ('Compliant', 'Compliant'),
        ('Pending Review', 'Pending Review'),
        ('Action Required', 'Action Required'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tax_profiles')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='tax_profiles')
    country = models.CharField(max_length=100)
    tax_id = models.CharField(max_length=100, blank=True)
    filing_status = models.CharField(max_length=20, choices=FILING_STATUS_CHOICES, default='Not Applicable')
    compliance_status = models.CharField(max_length=20, choices=COMPLIANCE_STATUS_CHOICES, default='Pending Review')
    notes = models.TextField(blank=True)
    last_reviewed = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['country', 'employee__name']

    def __str__(self):
        return f'{self.employee.name} — {self.country}'


class ComplianceEvent(models.Model):
    """The compliance-calendar half of "Multi-Currency Support &
    Compliance Calendar" — statutory filing/regulatory deadlines per
    country. Whether a non-completed event is "Due soon"/"Overdue" is
    computed live off `due_date` (serializer field), not stored."""

    CATEGORY_CHOICES = [
        ('Tax Filing', 'Tax Filing'),
        ('Currency Update', 'Currency Update'),
        ('Regulatory', 'Regulatory'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='compliance_events')
    country = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Tax Filing')
    due_date = models.DateField()
    # Nullable/blank — most regulatory deadlines (e.g. a filing) have no
    # dollar amount attached; only currency-update / payment-linked events
    # do, so this isn't forced to a fabricated 0.
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    responsible_party = models.CharField(max_length=150, blank=True)
    linked_payroll_run = models.ForeignKey(
        'PayrollRun', on_delete=models.SET_NULL, null=True, blank=True, related_name='compliance_events'
    )
    completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f'{self.country} — {self.title}'


class BankAccount(models.Model):
    """Direct Deposit / Banking Integration — stored and tracked for
    payroll purposes today; a real payment-rail integration (e.g. Plaid,
    Modern Treasury) is a drop-in-replaceable future upgrade, since no
    vendor account is provisioned for this project."""

    ACCOUNT_TYPE_CHOICES = [
        ('Checking', 'Checking'),
        ('Savings', 'Savings'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_accounts')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=150)
    bank_country = models.CharField(max_length=100, blank=True)
    account_holder_name = models.CharField(max_length=150)
    account_number_last4 = models.CharField(max_length=4)
    routing_number = models.CharField(max_length=20, blank=True)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='Checking')
    is_primary = models.BooleanField(default=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', 'bank_name']

    def __str__(self):
        return f'{self.employee.name} — {self.bank_name} ••••{self.account_number_last4}'


class BenefitPlan(models.Model):
    """Benefits Enrollment — the plan catalog side (what's on offer)."""

    PLAN_TYPE_CHOICES = [
        ('Health', 'Health'),
        ('Dental', 'Dental'),
        ('Vision', 'Vision'),
        ('Retirement', 'Retirement'),
        ('Life Insurance', 'Life Insurance'),
        ('Other', 'Other'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='benefit_plans')
    name = models.CharField(max_length=150)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, default='Health')
    provider = models.CharField(max_length=150, blank=True)
    employee_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    employer_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class BenefitEnrollment(models.Model):
    """Benefits Enrollment — the per-employee side (who's on what)."""

    COVERAGE_CHOICES = [
        ('Employee Only', 'Employee Only'),
        ('Employee + Spouse', 'Employee + Spouse'),
        ('Employee + Children', 'Employee + Children'),
        ('Family', 'Family'),
    ]
    STATUS_CHOICES = [
        ('Enrolled', 'Enrolled'),
        ('Pending', 'Pending'),
        ('Waived', 'Waived'),
        ('Terminated', 'Terminated'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='benefit_enrollments')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='benefit_enrollments')
    plan = models.ForeignKey(BenefitPlan, on_delete=models.CASCADE, related_name='enrollments')
    coverage_level = models.CharField(max_length=25, choices=COVERAGE_CHOICES, default='Employee Only')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Pending')
    enrolled_at = models.DateField(null=True, blank=True)
    terminated_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee.name} — {self.plan.name}'


class BenefitClaim(models.Model):
    """Claims & Reimbursement Workflows."""

    STATUS_CHOICES = [
        ('Submitted', 'Submitted'),
        ('Under Review', 'Under Review'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Paid', 'Paid'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='benefit_claims')
    employee = models.ForeignKey('people.Employee', on_delete=models.CASCADE, related_name='benefit_claims')
    plan = models.ForeignKey(BenefitPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='claims')
    claim_type = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Submitted')
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.employee.name} — {self.claim_type}'
