from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
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


class OwnedPayrollBenefitsViewSet(viewsets.ModelViewSet):
    """Shared base — every model in this app has its own `owner` field.
    Finance Admin gets the same full-tier access as HR/Admin across this
    whole app."""

    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class PayrollRunViewSet(OwnedPayrollBenefitsViewSet):
    """Finance Admin may create/update a payroll run, but can never mark it
    'Reconciled' themselves — that final sign-off stays HR/Admin-only, the
    "approval required" gate for payroll processing."""

    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer

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


class TaxProfileViewSet(viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = TaxProfile.objects.select_related('employee').all()
    serializer_class = TaxProfileSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class ComplianceEventViewSet(OwnedPayrollBenefitsViewSet):
    queryset = ComplianceEvent.objects.all()
    serializer_class = ComplianceEventSerializer


class BankAccountViewSet(viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = BankAccount.objects.select_related('employee').all()
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class BenefitPlanViewSet(OwnedPayrollBenefitsViewSet):
    queryset = BenefitPlan.objects.prefetch_related('enrollments').all()
    serializer_class = BenefitPlanSerializer


class BenefitEnrollmentViewSet(viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = BenefitEnrollment.objects.select_related('employee', 'plan').all()
    serializer_class = BenefitEnrollmentSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

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


class BenefitClaimViewSet(viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own
    department on top of HR/Admin/Finance Admin's full access."""

    queryset = BenefitClaim.objects.select_related('employee', 'plan').all()
    serializer_class = BenefitClaimSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdmin | IsDepartmentHeadReadOnly]

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
