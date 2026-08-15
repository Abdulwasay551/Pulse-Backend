from datetime import date

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import owner_scope_id
from it_assets.models import AssetIncident, AssetRecovery, BYODCompliance
from payroll_benefits.models import ComplianceEvent, PayrollRun
from people.models import LeaveRequest, Survey
from talent.models import Goal

from .health import compute_health


class OrgHealthView(APIView):
    """The admin dashboard's "ORG HEALTH" gauge — the same flag counts each
    module's own dashboard-summary endpoint already computes, reduced to one
    score via core.health.compute_health. Recomputed live on every request,
    same as everything else on this dashboard."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        uid = owner_scope_id(request)
        today = date.today()

        it_flags = {
            'non_compliant_byod': BYODCompliance.objects.filter(owner_id=uid, compliance_status='Non-Compliant').count(),
            'unresolved_incidents': AssetIncident.objects.filter(owner_id=uid, resolved=False).count(),
            'pending_recoveries': AssetRecovery.objects.filter(owner_id=uid, status='Pending').count(),
        }
        payroll_flags = {
            'discrepancies_flagged': PayrollRun.objects.filter(owner_id=uid, discrepancy_flagged=True).count(),
            'overdue_compliance': ComplianceEvent.objects.filter(owner_id=uid, completed=False, due_date__lt=today).count(),
        }
        people_flags = {
            'pending_leave': LeaveRequest.objects.filter(owner_id=uid, status='Pending').count(),
            'open_surveys': Survey.objects.filter(owner_id=uid, is_open=True).count(),
        }
        talent_flags = {
            'overdue_goals': Goal.objects.filter(owner_id=uid, target_date__lt=today).exclude(status='Completed').count(),
        }

        return Response(
            compute_health(
                {
                    'IT & Asset Management': it_flags,
                    'Payroll & Benefits': payroll_flags,
                    'People Management': people_flags,
                    'Talent Management': talent_flags,
                }
            )
        )
