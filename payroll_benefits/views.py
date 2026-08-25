from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access_matrix import matrix_permission, scoped_queryset
from core.activity import log_activity
from core.csv_io import CsvImportExportMixin, resolve_employee, resolve_related
from core.models import ActivityLog
from integrations.fx_provider import FxProviderError, fetch_live_rates
from integrations.wise_provider import WiseError
from integrations.wise_provider import get_quote as get_wise_quote
from core.permissions import (
    IsAuditorReadOnly,
    IsDepartmentHeadReadOnly,
    IsFinanceAdmin,
    IsHR,
    _role_is,
    is_hr_or_legacy,
    owner_scope_id,
)

from .models import (
    BankAccount,
    BenefitClaim,
    BenefitEnrollment,
    BenefitPlan,
    ComplianceEvent,
    ExchangeRate,
    PayrollRun,
    TaxProfile,
)
from .serializers import (
    BankAccountSerializer,
    BenefitClaimSerializer,
    BenefitEnrollmentSerializer,
    BenefitPlanSerializer,
    ComplianceEventSerializer,
    ExchangeRateSerializer,
    PayrollRunSerializer,
    TaxProfileSerializer,
)


def _resolve_plan(owner_id, raw_value):
    return resolve_related(BenefitPlan, owner_id, raw_value, match_fields=['name'], label='Benefit plan')


def _resolve_payroll_run(owner_id, raw_value):
    return resolve_related(PayrollRun, owner_id, raw_value, match_fields=['period'], label='Payroll run')


class IsHRReconcileOnly(BasePermission):
    """HR Admin's one deliberate write exception on Payroll Processing —
    signing a payroll run off as Reconciled is an approval action, not
    general edit rights, so it's carved out separately from the matrix's
    plain hra='R' code on PayrollRunViewSet below (everything else on this
    row stays read-only for HR). Finance Admin has full RWA on this app but
    is explicitly blocked from self-reconciling in perform_create/
    perform_update — reconciling is the one action only HR can take here.

    Grants a PUT/PATCH only when the submitted status is 'Reconciled' and
    the run isn't already reconciled. The frontend's edit form always
    resubmits every field together (period/contractors/amount/currency,
    not just status), so this doesn't require the request to omit them —
    only that the transition being requested is the sign-off itself."""

    def has_permission(self, request, view):
        return (
            is_hr_or_legacy(request)
            and request.method in ('PUT', 'PATCH')
            and request.data.get('status') == 'Reconciled'
        )

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == owner_scope_id(request) and obj.status != 'Reconciled'


class OwnedPayrollBenefitsViewSet(viewsets.ModelViewSet):
    """Shared base — every model in this app has its own `owner` field.
    Finance Admin has "full control across Payroll & Benefits" per the
    Control Hierarchy Matrix; HR Admin's matrix column here is mostly
    read-only (never full CRUD like it is in Recruit/People/Talent), so
    concrete subclasses below compose their own narrower
    matrix_permission(...) instead of inheriting a blanket HR grant."""

    permission_classes = [IsAuthenticated, IsFinanceAdmin]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class PayrollRunViewSet(CsvImportExportMixin, OwnedPayrollBenefitsViewSet):
    """Finance Admin may create/update a payroll run, but can never mark it
    'Reconciled' themselves — that final sign-off is HR Admin's one write
    exception on this otherwise read-only-for-HR row (IsHRReconcileOnly),
    the "approval required" gate for payroll processing."""

    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer
    # HR Admin: 'R' (read-only, not the full RWA it gets in Recruit/People/
    # Talent — narrowed to match the matrix) plus the one write exception
    # above. Auditor gets org-wide read (matrix: "Payroll Processing,
    # Payslips" / "Payroll Audit & Reconciliation Reports" rows). EMP/CON's
    # matrix R* ("own payslip") can't be implemented on this model —
    # PayrollRun is one row per company-wide pay run (aggregate amount/
    # contractor count), not a per-employee payslip; there's no employee FK
    # to self-scope by. See module report: would need a Payslip model (or
    # an employee FK + a per-employee amount field here) to grant that
    # slice for real.
    permission_classes = [
        IsAuthenticated,
        IsFinanceAdmin | IsHRReconcileOnly | matrix_permission(sa='RWA', hra='R', aud='R'),
    ]

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

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', hra='R', aud='R')

    def perform_create(self, serializer):
        if _role_is(self.request, 'Finance Admin') and serializer.validated_data.get('status') == 'Reconciled':
            raise PermissionDenied('Only HR can mark a payroll run as Reconciled.')
        run = serializer.save(owner_id=owner_scope_id(self.request))
        if run.status == 'Needs review':
            log_activity(owner_scope_id(self.request), f'{run.period} payroll needs review', 'amber')
        else:
            log_activity(owner_scope_id(self.request), f'{run.period} payroll processed', 'primary')

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        previous_flagged = serializer.instance.discrepancy_flagged
        new_status = serializer.validated_data.get('status', previous_status)
        if new_status == 'Reconciled' and previous_status != 'Reconciled' and _role_is(self.request, 'Finance Admin'):
            raise PermissionDenied('Only HR can mark a payroll run as Reconciled.')
        run = serializer.save()
        uid = owner_scope_id(self.request)
        # Audit trail — every status change and flag/unflag on a payroll
        # run gets its own activity-log entry (who did what, when), not
        # just the run's current state, so "Payroll audit trail should be
        # shown" has an actual history to show.
        if run.status != previous_status:
            if run.status == 'Reconciled':
                log_activity(uid, f'{run.period} payroll reconciled', 'primary')
            elif run.status == 'Needs review':
                log_activity(uid, f'{run.period} payroll flagged as needing review', 'amber')
        if run.discrepancy_flagged != previous_flagged:
            if run.discrepancy_flagged:
                log_activity(uid, f'{run.period} payroll discrepancy flagged', 'maroon')
            else:
                log_activity(uid, f'{run.period} payroll discrepancy unflagged', 'neutral')

    @action(detail=False, methods=['get'])
    def audit_trail(self, request):
        """The payroll-specific slice of the shared activity log — every
        entry logged by this ViewSet (created, flagged/unflagged,
        reconciled) uses "payroll" in its message, so filtering on that is
        enough to keep this scoped without a dedicated audit-log model."""
        uid = owner_scope_id(request)
        entries = ActivityLog.objects.filter(owner_id=uid, message__icontains='payroll')[:30]
        return Response(
            [{'id': e.id, 'message': e.message, 'tone': e.tone, 'created_at': e.created_at} for e in entries]
        )


class ExchangeRateViewSet(viewsets.ModelViewSet):
    """Multi-Currency Support's rate source — rates can be set by hand, or
    refreshed live via sync_live_rates below (Frankfurter/ECB reference
    rates, no API key needed), so `updated_at` reflects whichever the org
    last did."""

    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    # Matrix: "Multi-Currency Support & Compliance Calendar" — HR Admin 'R'
    # (narrowed from full RWA); Auditor org-wide read; no EMP/CON access at
    # all on this row.
    permission_classes = [IsAuthenticated, IsFinanceAdmin | matrix_permission(sa='RWA', hra='R', aud='R')]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', hra='R', aud='R')

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))

    @action(detail=False, methods=['get'])
    def convert(self, request):
        amount_raw = request.query_params.get('amount')
        from_currency = (request.query_params.get('from') or '').upper()
        to_currency = (request.query_params.get('to') or '').upper()
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            return Response({'detail': 'A numeric amount is required.'}, status=400)

        rates = {r.currency: float(r.rate_to_usd) for r in self.get_queryset()}
        rates.setdefault('USD', 1.0)
        if from_currency not in rates or to_currency not in rates:
            return Response(
                {'detail': 'No rate on file for one of these currencies yet — add it below first.'}, status=400
            )
        usd_value = amount * rates[from_currency]
        converted = usd_value / rates[to_currency]
        return Response({'amount': amount, 'from': from_currency, 'to': to_currency, 'result': round(converted, 2)})

    @action(detail=False, methods=['post'], url_path='sync-live-rates')
    def sync_live_rates(self, request):
        """Refreshes every currency this org already tracks against live
        rates — add a currency by hand first (even a placeholder rate of
        1), then sync to keep it current from then on."""
        uid = owner_scope_id(request)
        currencies = list(self.get_queryset().values_list('currency', flat=True))
        if not currencies:
            return Response({'detail': 'Add at least one currency first, then sync.'}, status=400)
        try:
            rates = fetch_live_rates(currencies)
        except FxProviderError as exc:
            return Response({'detail': str(exc)}, status=502)
        updated = []
        for code, rate in rates.items():
            # QuerySet.update() bypasses Model.save(), so auto_now wouldn't
            # otherwise touch updated_at — set it explicitly.
            ExchangeRate.objects.filter(owner_id=uid, currency=code).update(rate_to_usd=rate, updated_at=timezone.now())
            updated.append(code)
        return Response({'updated': updated})

    @action(detail=False, methods=['get'], url_path='wise-quote')
    def wise_quote(self, request):
        """A real, live Wise transfer quote — read-only, moves nothing.
        Complements convert() above: that's this org's own manually-set/
        synced rates, this is what an actual cross-border transfer would
        really cost right now via the org's connected Wise account."""
        amount_raw = request.query_params.get('amount')
        from_currency = (request.query_params.get('from') or '').upper()
        to_currency = (request.query_params.get('to') or '').upper()
        if not amount_raw or not from_currency or not to_currency:
            return Response({'detail': 'amount, from, and to are required.'}, status=400)
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            return Response({'detail': 'A numeric amount is required.'}, status=400)
        try:
            quote = get_wise_quote(owner_scope_id(request), from_currency, to_currency, amount)
        except WiseError as exc:
            return Response({'detail': str(exc), 'code': 'wise_not_configured'}, status=409)
        return Response(quote)


class TaxProfileViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = TaxProfile.objects.select_related('employee').all()
    serializer_class = TaxProfileSerializer
    # Matrix: "Multi-Country Tax Compliance" — HR Admin gets '-' (no access
    # at all, not even read — the one row in this module where even HR's
    # read is denied); Auditor gets org-wide read; no EMP/CON access on this
    # row (not even their own).
    permission_classes = [IsAuthenticated, IsFinanceAdmin | IsDepartmentHeadReadOnly | matrix_permission(sa='RWA', aud='R')]

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
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', aud='R')

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class ComplianceEventViewSet(CsvImportExportMixin, OwnedPayrollBenefitsViewSet):
    queryset = ComplianceEvent.objects.select_related('linked_payroll_run').all()
    serializer_class = ComplianceEventSerializer
    # Matrix: same "Multi-Currency Support & Compliance Calendar" row as
    # ExchangeRateViewSet (this is the calendar half) — HR Admin 'R'
    # (narrowed from full RWA); Auditor org-wide read, no EMP/CON access.
    permission_classes = [IsAuthenticated, IsFinanceAdmin | matrix_permission(sa='RWA', hra='R', aud='R')]

    csv_filename = 'compliance-events'
    csv_activity_label = 'compliance events'
    csv_import_fields = {
        'country': 'Country',
        'title': 'Title',
        'category': 'Category (Tax Filing, Currency Update, or Regulatory)',
        'due_date': 'Due date (YYYY-MM-DD)',
        'amount': 'Amount (optional)',
        'currency': 'Currency (3-letter code, optional)',
        'responsible_party': 'Responsible party',
        'linked_payroll_run': 'Linked payroll run (exact period, optional)',
        'completed': 'Completed (True or False)',
        'notes': 'Notes',
    }
    csv_required_fields = ['country', 'title', 'due_date']
    csv_field_parsers = {'linked_payroll_run': _resolve_payroll_run}
    csv_export_header = [
        'Country', 'Title', 'Category', 'Due date', 'Amount', 'Currency',
        'Responsible party', 'Linked payroll run', 'Completed',
    ]
    csv_sample_row = ['United States', 'Q3 payroll tax filing', 'Tax Filing', '2026-10-15', '', '', 'Finance Admin', '', 'False', '']

    def csv_export_row(self, e):
        return [
            e.country, e.title, e.category, e.due_date, e.amount, e.currency,
            e.responsible_party, e.linked_payroll_run.period if e.linked_payroll_run else '', e.completed,
        ]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', hra='R', aud='R')


class BankAccountViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = BankAccount.objects.select_related('employee').all()
    serializer_class = BankAccountSerializer
    # Matrix: "Direct Deposit / Banking Integration" — HR Admin gets '-' (no
    # access at all, same as Multi-Country Tax Compliance above); Auditor
    # org-wide read; Employee gets 'W*' (write only, own record — can
    # submit/update their own direct-deposit info but not read it back,
    # matching the matrix literally); Contractor gets none.
    permission_classes = [
        IsAuthenticated,
        IsFinanceAdmin | IsDepartmentHeadReadOnly | matrix_permission(sa='RWA', aud='R', emp='W*'),
    ]

    csv_filename = 'bank-accounts'
    csv_activity_label = 'bank accounts'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'bank_name': 'Bank name',
        'bank_country': 'Bank country',
        'account_holder_name': 'Account holder name',
        'account_number': 'Account number (full — only the last 4 digits are stored)',
        'routing_number': 'Routing number',
        'account_type': 'Account type (Checking or Savings)',
        'is_primary': 'Primary (True or False)',
        'verified': 'Verified (True or False)',
    }
    csv_required_fields = ['employee', 'bank_name', 'account_holder_name', 'account_number']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Bank name', 'Bank country', 'Account holder', 'Last 4', 'Type', 'Primary', 'Verified']
    csv_sample_row = ['Taylor Morgan', 'First National', 'United States', 'Taylor Morgan', '000123454321', '', 'Checking', 'True', 'False']

    def csv_export_row(self, b):
        return [
            b.employee.name, b.bank_name, b.bank_country, b.account_holder_name,
            b.account_number_last4, b.account_type, b.is_primary, b.verified,
        ]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', aud='R', emp='W*')

    def perform_create(self, serializer):
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role == 'Employee':
            # Self-service: can only ever submit banking info for
            # themselves, whatever `employee` was submitted.
            if not profile.employee_id:
                raise PermissionDenied('Your account has no linked employee record.')
            serializer.validated_data['employee'] = profile.employee
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role == 'Employee':
            # Never let a self-service update reassign the account to a
            # different employee.
            serializer.validated_data['employee'] = profile.employee
        serializer.save()


class BenefitPlanViewSet(CsvImportExportMixin, OwnedPayrollBenefitsViewSet):
    queryset = BenefitPlan.objects.prefetch_related('enrollments').all()
    serializer_class = BenefitPlanSerializer
    # Not its own matrix row — this is the plan catalog side of "Benefits
    # Enrollment" (BenefitEnrollmentViewSet below is the per-employee side).
    # HR Admin 'R' (narrowed from full RWA); Employee's matrix grant there
    # (RW*) is meaningless without being able to browse what's on offer
    # first, so Employee gets a plain 'R' here too (unstarred: the catalog
    # isn't per-employee data). Auditor org-wide read; Contractor gets none,
    # matching "Benefits Enrollment" CON='-'.
    permission_classes = [IsAuthenticated, IsFinanceAdmin | matrix_permission(sa='RWA', hra='R', aud='R', emp='R')]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', hra='R', aud='R', emp='R')

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
    # Matrix: "Benefits Enrollment" — HR Admin 'R' (narrowed from full RWA);
    # Auditor org-wide read; Employee gets real self-service (RW* — view +
    # enroll/change their own coverage); Contractor gets none.
    permission_classes = [
        IsAuthenticated,
        IsFinanceAdmin | IsDepartmentHeadReadOnly | matrix_permission(sa='RWA', hra='R', aud='R', emp='RW*'),
    ]

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
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', hra='R', aud='R', emp='RW*')

    def perform_create(self, serializer):
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role == 'Employee':
            # Self-service: can only ever enroll themselves, whatever
            # `employee` was submitted.
            if not profile.employee_id:
                raise PermissionDenied('Your account has no linked employee record.')
            serializer.validated_data['employee'] = profile.employee
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
    # Matrix: "Claims, Reimbursement & Bonus Workflows" — HR Admin 'R'
    # (narrowed from full RWA — approving/resolving a claim is now Finance
    # Admin's or the claimant's Manager's job, not HR's); Auditor org-wide
    # read; Manager gets 'A*' (approve their own team's claims — covered by
    # matrix_permission treating Approve as read+write, gated to the team);
    # Employee/Contractor get 'W*' (submit their own claim, write only, per
    # the matrix literally — core/my_views.py's MyBenefitClaimsView already
    # gives an Employee read+write on their own claims via a dedicated
    # self-service endpoint; this generic viewset grant is added for
    # consistency with the matrix, same as AttendanceRecord in People).
    permission_classes = [
        IsAuthenticated,
        IsFinanceAdmin
        | IsDepartmentHeadReadOnly
        | matrix_permission(sa='RWA', hra='R', aud='R', mgr='A*', emp='W*', con='W*'),
    ]

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
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, sa='RWA', hra='R', aud='R', mgr='A*', emp='W*', con='W*')

    def perform_create(self, serializer):
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role in ('Employee', 'Contractor'):
            # Self-service: can only ever file a claim for themselves,
            # whatever `employee` was submitted.
            if not profile.employee_id:
                raise PermissionDenied('Your account has no linked employee record.')
            serializer.validated_data['employee'] = profile.employee
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
    user's own rows — nothing here is stored/cached. Covers both the
    matrix's "Overview" row and its "Benefit Cost Analysis" row (this one
    endpoint returns both payloads together) — Auditor gets read on both via
    IsAuditorReadOnly. "Benefit Cost Analysis" also gives Manager a plain
    'R', but that isn't implemented here: this view computes tenant-wide
    aggregates with no per-team filtering of enrollments/plans, and this
    same endpoint also carries the Overview payload (which Manager gets no
    access to at all) — splitting/team-scoping the cost-analysis half
    cleanly would need a dedicated endpoint or real aggregation-level team
    filtering, which is more than an additive permission change; flagged in
    the module report rather than approximated here."""

    permission_classes = [IsAuthenticated, IsHR | IsFinanceAdmin | IsAuditorReadOnly]

    def get(self, request):
        uid = owner_scope_id(request)
        runs = PayrollRun.objects.filter(owner_id=uid)
        enrollments = BenefitEnrollment.objects.filter(owner_id=uid)
        claims = BenefitClaim.objects.filter(owner_id=uid)
        plans = BenefitPlan.objects.filter(owner_id=uid)

        latest_run = runs.first()
        needs_review = runs.filter(status='Needs review').count()
        pending_claims = claims.filter(status__in=['Submitted', 'Under Review']).count()
        active_enrollments = enrollments.filter(status='Enrolled').count()
        discrepancies_flagged = runs.filter(discrepancy_flagged=True).count()
        overdue_compliance = ComplianceEvent.objects.filter(
            owner_id=uid, completed=False, due_date__lt=timezone.now().date()
        ).count()
        total_benefit_cost = sum(
            (e.plan.employer_cost for e in enrollments.filter(status='Enrolled').select_related('plan')),
            start=0,
        )

        # Payroll cost trend — last 6 runs, oldest first, for the Overview
        # page's analytical chart (replaces the flat "Compliance & audit
        # KPIs" grid per the change-request doc).
        recent_runs = list(runs[:6])
        recent_runs.reverse()
        payroll_trend = [
            {'label': r.period, 'value': float(r.amount), 'currency': r.currency}
            for r in recent_runs
        ]

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
                'flags': {
                    'discrepancies_flagged': discrepancies_flagged,
                    'overdue_compliance': overdue_compliance,
                },
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
                'benefit_cost_by_department': _group_enrollment_cost(enrollments, 'employee__department'),
                'benefit_cost_by_location': _group_enrollment_cost(enrollments, 'employee__location'),
                'benefit_cost_by_employee': _group_enrollment_cost_by_employee(enrollments),
                'total_monthly_benefit_cost': float(total_benefit_cost),
                'payroll_trend': payroll_trend,
            }
        )


def _group_enrollment_cost(enrollments, group_field):
    """Employer benefit cost summed per distinct value of `group_field`
    (e.g. employee__department, employee__location) — used for the Benefit
    Cost Analysis page's "division by employee/department/region" request.
    Blank/missing values are grouped under "Unspecified" rather than
    silently dropped."""
    enrolled = enrollments.filter(status='Enrolled').select_related('plan', 'employee')
    totals = {}
    for e in enrolled:
        key = getattr(e.employee, group_field.split('__')[1]) or 'Unspecified'
        totals[key] = totals.get(key, 0) + e.plan.employer_cost
    return [{'label': label, 'value': float(value)} for label, value in sorted(totals.items(), key=lambda kv: -kv[1])]


def _group_enrollment_cost_by_employee(enrollments, limit=10):
    """Same as _group_enrollment_cost, but per employee (by name) — the
    "by employee" half of the Benefit Cost Analysis breakdown request,
    capped to the top spenders so the page doesn't render one row per
    employee in a large org."""
    enrolled = enrollments.filter(status='Enrolled').select_related('plan', 'employee')
    totals = {}
    for e in enrolled:
        totals[e.employee.name] = totals.get(e.employee.name, 0) + e.plan.employer_cost
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:limit]
    return [{'label': label, 'value': float(value)} for label, value in ranked]
