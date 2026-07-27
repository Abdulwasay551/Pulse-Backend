from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.permissions import IsHR, IsOwner

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
    """Shared base — every model in this app has its own `owner` field."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class PayrollRunViewSet(OwnedPayrollBenefitsViewSet):
    queryset = PayrollRun.objects.all()
    serializer_class = PayrollRunSerializer

    def perform_create(self, serializer):
        run = serializer.save(owner=self.request.user)
        if run.status == 'Needs review':
            log_activity(self.request.user, f'{run.period} payroll needs review', 'amber')
        else:
            log_activity(self.request.user, f'{run.period} payroll processed', 'primary')


class TaxProfileViewSet(OwnedPayrollBenefitsViewSet):
    queryset = TaxProfile.objects.select_related('employee').all()
    serializer_class = TaxProfileSerializer


class ComplianceEventViewSet(OwnedPayrollBenefitsViewSet):
    queryset = ComplianceEvent.objects.all()
    serializer_class = ComplianceEventSerializer


class BankAccountViewSet(OwnedPayrollBenefitsViewSet):
    queryset = BankAccount.objects.select_related('employee').all()
    serializer_class = BankAccountSerializer


class BenefitPlanViewSet(OwnedPayrollBenefitsViewSet):
    queryset = BenefitPlan.objects.prefetch_related('enrollments').all()
    serializer_class = BenefitPlanSerializer


class BenefitEnrollmentViewSet(OwnedPayrollBenefitsViewSet):
    queryset = BenefitEnrollment.objects.select_related('employee', 'plan').all()
    serializer_class = BenefitEnrollmentSerializer

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        instance = serializer.save()
        if previous_status != 'Enrolled' and instance.status == 'Enrolled' and not instance.enrolled_at:
            instance.enrolled_at = timezone.now().date()
            instance.save(update_fields=['enrolled_at'])
        if previous_status != 'Terminated' and instance.status == 'Terminated' and not instance.terminated_at:
            instance.terminated_at = timezone.now().date()
            instance.save(update_fields=['terminated_at'])


class BenefitClaimViewSet(OwnedPayrollBenefitsViewSet):
    queryset = BenefitClaim.objects.select_related('employee', 'plan').all()
    serializer_class = BenefitClaimSerializer

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        instance = serializer.save()
        if previous_status not in ('Approved', 'Rejected', 'Paid') and instance.status in ('Approved', 'Rejected', 'Paid'):
            instance.resolved_at = timezone.now()
            instance.save(update_fields=['resolved_at'])
            log_activity(self.request.user, f'{instance.claim_type} claim {instance.status.lower()}', 'primary')


class PayrollBenefitsDashboardSummaryView(APIView):
    """EVO-Payroll & Benefits' overview numbers, computed live from the
    user's own rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated, IsHR]

    def get(self, request):
        user = request.user
        runs = PayrollRun.objects.filter(owner=user)
        tax_profiles = TaxProfile.objects.filter(owner=user)
        events = ComplianceEvent.objects.filter(owner=user, completed=False)
        enrollments = BenefitEnrollment.objects.filter(owner=user)
        claims = BenefitClaim.objects.filter(owner=user)
        plans = BenefitPlan.objects.filter(owner=user)

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
