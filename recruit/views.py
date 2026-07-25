from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.models import ActivityLog
from core.permissions import IsOwner
from payroll_benefits.models import PayrollRun

from .models import Candidate, Client, Requisition
from .serializers import CandidateSerializer, ClientSerializer, RequisitionSerializer


class OwnedModelViewSet(viewsets.ModelViewSet):
    """Every Recruit resource is scoped to its owner, both for listing and
    for object-level access — shared here so each viewset only adds what's
    specific to it."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ClientViewSet(OwnedModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer

    def perform_create(self, serializer):
        client = serializer.save(owner=self.request.user)
        log_activity(self.request.user, f'New client added: {client.name}', 'neutral')


class RequisitionViewSet(OwnedModelViewSet):
    queryset = Requisition.objects.select_related('client').all()
    serializer_class = RequisitionSerializer

    def perform_create(self, serializer):
        requisition = serializer.save(owner=self.request.user)
        log_activity(
            self.request.user,
            f'New requisition opened: {requisition.title} at {requisition.client.name}',
            'neutral',
        )


class CandidateViewSet(OwnedModelViewSet):
    queryset = Candidate.objects.select_related('client', 'requisition').all()
    serializer_class = CandidateSerializer

    def perform_create(self, serializer):
        candidate = serializer.save(owner=self.request.user)
        log_activity(self.request.user, f'{candidate.name} added as a candidate for {candidate.role}', 'neutral')

    def perform_update(self, serializer):
        previous_stage = serializer.instance.stage
        candidate = serializer.save()
        if candidate.stage != previous_stage:
            if candidate.stage == 'Placed':
                log_activity(self.request.user, f'{candidate.name} placed as {candidate.role}', 'primary')
            elif candidate.stage == 'Rejected':
                log_activity(self.request.user, f'{candidate.name} marked not a fit for {candidate.role}', 'maroon')
            elif candidate.stage == 'Offer':
                log_activity(self.request.user, f'Offer sent to {candidate.name} for {candidate.role}', 'primary')
            else:
                log_activity(
                    self.request.user,
                    f'{candidate.name} advanced to {candidate.stage} for {candidate.role}',
                    'primary',
                )


def _add_months(d, months):
    """Same day-of-month `months` away, clamped to the 1st — every caller
    here only ever needs month boundaries, never a specific day."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return d.replace(year=year, month=month, day=1)


def _relative_time(dt):
    delta = timezone.now() - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        return f'{int(seconds // 60)}m ago'
    if seconds < 86400:
        return f'{int(seconds // 3600)}h ago'
    return f'{int(seconds // 86400)}d ago'


class DashboardSummaryView(APIView):
    """EVO-Recruit's overview/analytics numbers, computed live from the
    user's own data — nothing here is stored/cached. "Revenue this month"
    reads from payroll_benefits.PayrollRun since placement-fee revenue is
    tracked as payroll, not as a Recruit-owned figure."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        candidates = Candidate.objects.filter(owner=user)
        requisitions = Requisition.objects.filter(owner=user)
        payroll_runs = PayrollRun.objects.filter(owner=user)

        today = timezone.now().date()
        month_start = today.replace(day=1)
        last_month_start = _add_months(month_start, -1)
        last_month_end = month_start - timedelta(days=1)
        week_ago = today - timedelta(days=7)

        open_requisitions = requisitions.filter(status__in=Requisition.OPEN_STATUSES).count()
        open_requisitions_new = requisitions.filter(
            status__in=Requisition.OPEN_STATUSES, posted_at__gte=week_ago
        ).count()

        active_candidates = candidates.exclude(stage__in=['Placed', 'Rejected']).count()
        active_candidates_new = candidates.filter(
            created_at__date__gte=week_ago
        ).exclude(stage__in=['Placed', 'Rejected']).count()

        placements_this_month = candidates.filter(stage='Placed', placed_at__gte=month_start).count()
        placements_last_month = candidates.filter(
            stage='Placed', placed_at__gte=last_month_start, placed_at__lte=last_month_end
        ).count()
        placements_change = (
            f'+{round((placements_this_month - placements_last_month) / placements_last_month * 100)}% vs last month'
            if placements_last_month
            else ('+100% vs last month' if placements_this_month else 'No change vs last month')
        )

        revenue_this_month = payroll_runs.filter(created_at__date__gte=month_start).aggregate(total=Sum('amount'))[
            'total'
        ] or 0

        overview_stats = [
            {
                'label': 'Open requisitions',
                'value': str(open_requisitions),
                'change': f'+{open_requisitions_new} this week',
                'href': '/dashboard/requisitions',
            },
            {
                'label': 'Active candidates',
                'value': str(active_candidates),
                'change': f'+{active_candidates_new} this week',
                'href': '/dashboard/candidates',
            },
            {
                'label': 'Placements this month',
                'value': str(placements_this_month),
                'change': placements_change,
                'href': '/dashboard/analytics',
            },
            {
                'label': 'Revenue this month',
                'value': f'${revenue_this_month:,.0f}',
                'change': 'placement fees',
                'href': '/dashboard/payroll',
            },
        ]

        pipeline_stages = [
            {'label': stage, 'count': candidates.filter(stage=stage).count()}
            for stage in ['Sourced', 'Interview', 'Offer', 'Placed']
        ]

        total_sourced = candidates.count()
        source_breakdown = []
        if total_sourced:
            for source_value, source_label in Candidate.SOURCE_CHOICES:
                count = candidates.filter(source=source_value).count()
                if count:
                    source_breakdown.append(
                        {'label': source_label, 'percent': round(count / total_sourced * 100)}
                    )

        placements_trend = []
        for i in range(5, -1, -1):
            month_date = _add_months(month_start, -i)
            month_end = _add_months(month_date, 1) - timedelta(days=1)
            count = candidates.filter(stage='Placed', placed_at__gte=month_date, placed_at__lte=month_end).count()
            placements_trend.append({'month': month_date.strftime('%b'), 'value': count})

        recent_activity = [
            {
                'id': str(item.id),
                'message': item.message,
                'time': _relative_time(item.created_at),
                'tone': item.tone,
            }
            for item in ActivityLog.objects.filter(owner=user)[:6]
        ]

        return Response(
            {
                'overview_stats': overview_stats,
                'pipeline_stages': pipeline_stages,
                'source_breakdown': source_breakdown,
                'placements_trend': placements_trend,
                'recent_activity': recent_activity,
            }
        )
