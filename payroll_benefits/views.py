from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.csv_io import CsvImportExportMixin, resolve_employee, resolve_related
from core.permissions import (
    IsDepartmentHeadReadOnly,
    IsFinanceAdmin,
    IsHR,
    IsOwner,
    _role_is,
    owner_scope_id,
)

from .models import (
    BankAccount,
    BenefitClaim,
    BenefitEnrollment,
    BenefitPlan,
    ComplianceEvent,
    PayrollRun,
    TaxProfile,
)
from .serializers import (
    BankAccountSerializer,
    BenefitClaimSerializer,
    BenefitEnrollmentSerializer,
    BenefitPlanSerializer,
    ComplianceEventSerializer,
    PayrollRunSerializer,
    TaxProfileSerializer,
)


def _resolve_plan(owner_id, raw_value):
    return resolve_related(BenefitPlan, owner_id, raw_value, match_fields=['name'], label='Benefit plan')


class OwnedPayrollBenefitsViewSet(viewsets.ModelViewSet):
    """Shared base — every model in this app has its own `owner` field.
    Finance Admin gets the same full-tier access as HR/Admin across this
    whole app."""

    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class PayrollRunViewSet(CsvImportExportMixin, OwnedPayrollBenefitsViewSet):
    """Finance Admin may create/update a payroll run, but can never mark it
    'Reconciled' themselves — that final sign-off stays HR/Admin-only, the
    "approval required" gate for payroll processing."""

    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer

    csv_filename = 'payroll-runs'
    csv_activity_label = 'payroll runs'
    csv_import_fields = {
        'period': 'Period (e.g. "August 2026")',
        'contractors': 'Contractors',
        'amount': 'Amount',
        'currency': 'Currency (3-letter code, e.g. USD)',
        'status': 'Status (Processing, Needs review, or Reconciled)',
        'discrepancy_flagged': 'Discrepancy flagged (True or False)',
        'audit_notes': 'Audit notes',
    }
    csv_required_fields = ['period']
    csv_export_header = ['Period', 'Contractors', 'Amount', 'Currency', 'Status', 'Discrepancy flagged']
    csv_sample_row = ['August 2026', '3', '145000', 'USD', 'Processing', 'False', '']

    def csv_export_row(self, r):
        return [r.period, r.contractors, r.amount, r.currency, r.status, r.discrepancy_flagged]

    def perform_create(self, serializer):
        if _role_is(self.request, 'Finance Admin') and serializer.validated_data.get('status') == 'Reconciled':
            raise PermissionDenied('Only HR or an Admin can mark a payroll run as Reconciled.')
        run = serializer.save(owner_id=owner_scope_id(self.request))
        if run.status == 'Needs review':
            log_activity(owner_scope_id(self.request), f'{run.period} payroll needs review', 'amber')
        else:
            log_activity(owner_scope_id(self.request), f'{run.period} payroll processed', 'primary')

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        new_status = serializer.validated_data.get('status', previous_status)
        if new_status == 'Reconciled' and previous_status != 'Reconciled' and _role_is(self.request, 'Finance Admin'):
            raise PermissionDenied('Only HR or an Admin can mark a payroll run as Reconciled.')
        serializer.save()


class TaxProfileViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = TaxProfile.objects.select_related('employee').all()
    serializer_class = TaxProfileSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

    csv_filename = 'tax-profiles'
    csv_activity_label = 'tax profiles'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'country': 'Country',
        'tax_id': 'Tax ID',
        'filing_status': 'Filing status (Single, Married, Head of Household, or Not Applicable)',
        'compliance_status': 'Compliance status (Compliant, Pending Review, or Action Required)',
        'notes': 'Notes',
        'last_reviewed': 'Last reviewed (YYYY-MM-DD)',
    }
    csv_required_fields = ['employee', 'country']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Country', 'Tax ID', 'Filing status', 'Compliance status', 'Last reviewed']
    csv_sample_row = ['Taylor Morgan', 'United States', '', 'Single', 'Compliant', '', '2026-06-01']

    def csv_export_row(self, t):
        return [t.employee.name, t.country, t.tax_id, t.filing_status, t.compliance_status, t.last_reviewed]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class ComplianceEventViewSet(CsvImportExportMixin, OwnedPayrollBenefitsViewSet):
    queryset = ComplianceEvent.objects.all()
    serializer_class = ComplianceEventSerializer

    csv_filename = 'compliance-events'
    csv_activity_label = 'compliance events'
    csv_import_fields = {
        'country': 'Country',
        'title': 'Title',
        'category': 'Category (Tax Filing, Currency Update, or Regulatory)',
        'due_date': 'Due date (YYYY-MM-DD)',
        'completed': 'Completed (True or False)',
        'notes': 'Notes',
    }
    csv_required_fields = ['country', 'title', 'due_date']
    csv_export_header = ['Country', 'Title', 'Category', 'Due date', 'Completed']
    csv_sample_row = ['United States', 'Q3 payroll tax filing', 'Tax Filing', '2026-10-15', 'False', '']

    def csv_export_row(self, e):
        return [e.country, e.title, e.category, e.due_date, e.completed]


class BankAccountViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = BankAccount.objects.select_related('employee').all()
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

    csv_filename = 'bank-accounts'
    csv_activity_label = 'bank accounts'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'bank_name': 'Bank name',
        'account_holder_name': 'Account holder name',
        'account_number': 'Account number (full — only the last 4 digits are stored)',
        'routing_number': 'Routing number',
        'account_type': 'Account type (Checking or Savings)',
        'is_primary': 'Primary (True or False)',
        'verified': 'Verified (True or False)',
    }
    csv_required_fields = ['employee', 'bank_name', 'account_holder_name', 'account_number']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Bank name', 'Account holder', 'Last 4', 'Type', 'Primary', 'Verified']
    csv_sample_row = ['Taylor Morgan', 'First National', 'Taylor Morgan', '000123454321', '', 'Checking', 'True', 'False']

    def csv_export_row(self, b):
        return [b.employee.name, b.bank_name, b.account_holder_name, b.account_number_last4, b.account_type, b.is_primary, b.verified]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class BenefitPlanViewSet(CsvImportExportMixin, OwnedPayrollBenefitsViewSet):
    queryset = BenefitPlan.objects.prefetch_related('enrollments').all()
    serializer_class = BenefitPlanSerializer

    csv_filename = 'benefit-plans'
    csv_activity_label = 'benefit plans'
    csv_import_fields = {
        'name': 'Plan name',
        'plan_type': 'Type (Health, Dental, Vision, Retirement, Life Insurance, or Other)',
        'provider': 'Provider',
        'employee_cost': 'Employee cost',
        'employer_cost': 'Employer cost',
        'description': 'Description',
        'is_active': 'Active (True or False)',
    }
    csv_required_fields = ['name']
    csv_export_header = ['Name', 'Type', 'Provider', 'Employee cost', 'Employer cost', 'Active']
    csv_sample_row = ['PPO Gold', 'Health', 'Anthem', '120', '480', 'Preferred provider organization plan.', 'True']

    def csv_export_row(self, p):
        return [p.name, p.plan_type, p.provider, p.employee_cost, p.employer_cost, p.is_active]


class BenefitEnrollmentViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = BenefitEnrollment.objects.select_related('employee', 'plan').all()
    serializer_class = BenefitEnrollmentSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

    csv_filename = 'benefit-enrollments'
    csv_activity_label = 'benefit enrollments'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'plan': 'Plan (exact name)',
        'coverage_level': 'Coverage level (Employee Only, Employee + Spouse, Employee + Children, or Family)',
        'status': 'Status (Enrolled, Pending, Waived, or Terminated)',
    }
    csv_required_fields = ['employee', 'plan']
    csv_field_parsers = {'employee': resolve_employee, 'plan': _resolve_plan}
    csv_export_header = ['Employee', 'Plan', 'Coverage level', 'Status', 'Enrolled at']
    csv_sample_row = ['Taylor Morgan', 'PPO Gold', 'Employee Only', 'Enrolled']

    def csv_export_row(self, e):
        return [e.employee.name, e.plan.name, e.coverage_level, e.status, e.enrolled_at]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        instance = serializer.save()
        if previous_status != 'Enrolled' and instance.status == 'Enrolled' and not instance.enrolled_at:
            instance.enrolled_at = timezone.now().date()
            instance.save(update_fields=['enrolled_at'])
        if previous_status != 'Terminated' and instance.status == 'Terminated' and not instance.terminated_at:
            instance.terminated_at = timezone.now().date()
            instance.save(update_fields=['terminated_at'])


class BenefitClaimViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = BenefitClaim.objects.select_related('employee', 'plan').all()
    serializer_class = BenefitClaimSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

    csv_filename = 'benefit-claims'
    csv_activity_label = 'benefit claims'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'plan': 'Plan (exact name, optional)',
        'claim_type': 'Claim type',
        'amount': 'Amount',
        'description': 'Description',
        'status': 'Status (Submitted, Under Review, Approved, Rejected, or Paid)',
    }
    csv_required_fields = ['employee', 'claim_type', 'amount']
    csv_field_parsers = {'employee': resolve_employee, 'plan': _resolve_plan}
    csv_export_header = ['Employee', 'Plan', 'Claim type', 'Amount', 'Status', 'Submitted at']
    csv_sample_row = ['Taylor Morgan', 'PPO Gold', 'Dental cleaning', '150', 'Submitted', '']

    def csv_export_row(self, c):
        return [c.employee.name, c.plan.name if c.plan else '', c.claim_type, c.amount, c.status, c.submitted_at]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        instance = serializer.save()
        if previous_status not in ('Approved', 'Rejected', 'Paid') and instance.status in ('Approved', 'Rejected', 'Paid'):
            instance.resolved_at = timezone.now()
            instance.save(update_fields=['resolved_at'])
            log_activity(owner_scope_id(self.request), f'{instance.claim_type} claim {instance.status.lower()}', 'primary')


class PayrollBenefitsDashboardSummaryView(APIView):
    """EVO-Payroll & Benefits' overview numbers, computed live from the
    user's own rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated, IsHR | IsFinanceAdmin]

    def get(self, request):
        uid = owner_scope_id(request)
        runs = PayrollRun.objects.filter(owner_id=uid)
        tax_profiles = TaxProfile.objects.filter(owner_id=uid)
        events = ComplianceEvent.objects.filter(owner_id=uid, completed=False)
        enrollments = BenefitEnrollment.objects.filter(owner_id=uid)
        claims = BenefitClaim.objects.filter(owner_id=uid)
        plans = BenefitPlan.objects.filter(owner_id=uid)

        latest_run = runs.first()
        needs_review = runs.filter(status='Needs review').count()
        flagged = runs.filter(discrepancy_flagged=True).count()
        action_required = tax_profiles.filter(compliance_status='Action Required').count()

        from datetime import date, timedelta
        today = date.today()
        overdue_events = sum(1 for e in events if e.due_date < today)
        due_soon_events = sum(1 for e in events if today <= e.due_date <= today + timedelta(days=14))

        pending_claims = claims.filter(status__in=['Submitted', 'Under Review']).count()
        active_enrollments = enrollments.filter(status='Enrolled').count()
        total_benefit_cost = sum(
            (e.plan.employer_cost for e in enrollments.filter(status='Enrolled').select_related('plan')),
            start=0,
        )

        return Response(
            {
                'overview_stats': [
                    {
                        'label': 'Latest payroll run',
                        'value': latest_run.period if latest_run else '—',
                        'change': '',
                        'href': '/dashboard/payroll',
                    },
                    {'label': 'Runs needing review', 'value': str(needs_review), 'change': '', 'href': '/dashboard/payroll'},
                    {'label': 'Active benefit enrollments', 'value': str(active_enrollments), 'change': '', 'href': '/dashboard/benefits-enrollment'},
                    {'label': 'Pending claims', 'value': str(pending_claims), 'change': '', 'href': '/dashboard/claims'},
                ],
                'kpis': [
                    {'label': 'Discrepancies flagged', 'value': str(flagged), 'href': '/dashboard/payroll-audit'},
                    {'label': 'Tax action required', 'value': str(action_required), 'href': '/dashboard/tax-compliance'},
                    {'label': 'Compliance events overdue', 'value': str(overdue_events), 'href': '/dashboard/compliance-calendar'},
                    {'label': 'Due within 14 days', 'value': str(due_soon_events), 'href': '/dashboard/compliance-calendar'},
                ],
                'benefit_cost_by_type': [
                    {
                        'label': plan_type,
                        'value': float(
                            sum(
                                p.employer_cost * p.enrollments.filter(status='Enrolled').count()
                                for p in plans.filter(plan_type=plan_type)
                            )
                        ),
                    }
                    for plan_type, _ in BenefitPlan.PLAN_TYPE_CHOICES
                    if plans.filter(plan_type=plan_type).exists()
                ],
                'total_monthly_benefit_cost': float(total_benefit_cost),
            }
        )
