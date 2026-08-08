from datetime import timedelta

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.csv_io import CsvImportExportMixin, resolve_related
from core.models import ActivityLog
from core.permissions import (
    IsDepartmentHeadReadOnly,
    IsDepartmentHeadRequisitionAccess,
    IsHR,
    IsITManagerTaskAccess,
    IsOwner,
    IsRecruiter,
    _role_is,
    owner_scope_id,
)
from payroll_benefits.models import PayrollRun

from .ai_screening import score_candidate
from .models import (
    BackgroundCheck,
    Candidate,
    Client,
    Offboarding,
    OffboardingTask,
    OfferLetter,
    Onboarding,
    OnboardingTask,
    Requisition,
)
from .serializers import (
    BackgroundCheckSerializer,
    CandidatePortalSerializer,
    CandidateSerializer,
    ClientSerializer,
    OffboardingSerializer,
    OffboardingTaskSerializer,
    OfferLetterSerializer,
    OnboardingSerializer,
    OnboardingTaskSerializer,
    RequisitionSerializer,
)

def _resolve_client(owner_id, raw_value):
    return resolve_related(Client, owner_id, raw_value, match_fields=['name'], label='Client')


def _resolve_candidate(owner_id, raw_value):
    return resolve_related(Candidate, owner_id, raw_value, match_fields=['email', 'name'], label='Candidate')


class OwnedModelViewSet(viewsets.ModelViewSet):
    """Every Recruit resource is scoped to its owner, both for listing and
    for object-level access — shared here so each viewset only adds what's
    specific to it. Recruiter gets the same full-tier access as HR/Admin
    across this whole app."""

    permission_classes = [IsAuthenticated, IsOwner | IsRecruiter]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class ClientViewSet(CsvImportExportMixin, OwnedModelViewSet):
    """Department Head gets read-only access on top of HR/Admin/Recruiter's
    full access — needed to populate the client picker when they create a
    Requisition ("request for recruit"), even though they otherwise have no
    Recruit access at all."""

    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsRecruiter | IsDepartmentHeadReadOnly]

    csv_filename = 'clients'
    csv_activity_label = 'clients'
    csv_import_fields = {
        'name': 'Name',
        'industry': 'Industry',
        'contact_name': 'Contact name',
        'contact_email': 'Contact email',
        'status': 'Status (Active, Prospect, or At risk)',
    }
    csv_required_fields = ['name']
    csv_export_header = ['Name', 'Industry', 'Contact name', 'Contact email', 'Status']
    csv_sample_row = ['Acme Corp', 'Manufacturing', 'Jordan Lee', 'jordan@acme.com', 'Active']

    def get_csv_export_queryset(self):
        return self.get_queryset().order_by('name')

    def csv_export_row(self, c):
        return [c.name, c.industry, c.contact_name, c.contact_email, c.status]

    def perform_create(self, serializer):
        client = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'New client added: {client.name}', 'neutral')


class RequisitionViewSet(CsvImportExportMixin, OwnedModelViewSet):
    """Department Head may also view every requisition and create new ones
    ("request for recruit") on top of HR/Admin/Recruiter's full access —
    never update/delete an existing one."""

    queryset = Requisition.objects.select_related('client').all()
    serializer_class = RequisitionSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsRecruiter | IsDepartmentHeadRequisitionAccess]

    csv_filename = 'job-openings'
    csv_activity_label = 'job openings'
    csv_import_fields = {
        'client': 'Client (exact name)',
        'title': 'Role title',
        'recruiter': 'Recruiter',
        'priority': 'Priority (High, Medium, or Low)',
        'status': 'Status (Open, Interviewing, Offer stage, On hold, or Filled)',
        'requirements': 'Requirements',
    }
    csv_required_fields = ['client', 'title']
    csv_field_parsers = {'client': _resolve_client}
    csv_export_header = ['Client', 'Role title', 'Recruiter', 'Priority', 'Status', 'Posted', 'Candidates']
    csv_sample_row = ['Acme Corp', 'Senior QA Engineer', 'Alex Rivera', 'High', 'Open', 'Python, React, 3+ years experience']

    def csv_export_row(self, r):
        return [r.client.name, r.title, r.recruiter, r.priority, r.status, r.posted_at, r.candidates.count()]

    def perform_create(self, serializer):
        requisition = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(
            owner_scope_id(self.request),
            f'New requisition opened: {requisition.title} at {requisition.client.name}',
            'neutral',
        )


class CandidateViewSet(CsvImportExportMixin, OwnedModelViewSet):
    queryset = Candidate.objects.select_related('client', 'requisition').all()
    serializer_class = CandidateSerializer

    csv_filename = 'candidates'
    csv_activity_label = 'candidates'
    csv_import_fields = {
        'name': 'Name',
        'role': 'Current position',
        'email': 'Email',
        'phone': 'Phone',
        'stage': 'Stage (Sourced, Interview, Offer, Placed, or Rejected)',
        'source': 'Source (LinkedIn, Referral, Job Board, Sourced, or Other)',
        'current_salary': 'Current salary',
        'applied_at': 'Applied at (YYYY-MM-DD)',
    }
    csv_required_fields = ['name', 'role']
    csv_export_header = ['Name', 'Role', 'Email', 'Phone', 'Stage', 'Source', 'Applied at', 'AI score']
    csv_sample_row = ['Jamie Chen', 'QA Engineer', 'jamie.chen@example.com', '+1 555-0100', 'Sourced', 'LinkedIn', '75000', '2026-08-01']

    def get_csv_export_queryset(self):
        return self.get_queryset().order_by('name')

    def csv_export_row(self, c):
        return [c.name, c.role, c.email, c.phone, c.stage, c.source, c.applied_at, c.ai_score]

    def perform_create(self, serializer):
        candidate = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'{candidate.name} added as a candidate for {candidate.role}', 'neutral')

    def perform_update(self, serializer):
        previous_stage = serializer.instance.stage
        candidate = serializer.save()
        uid = owner_scope_id(self.request)
        if candidate.stage != previous_stage:
            if candidate.stage == 'Placed':
                log_activity(uid, f'{candidate.name} placed as {candidate.role}', 'primary')
            elif candidate.stage == 'Rejected':
                log_activity(uid, f'{candidate.name} marked not a fit for {candidate.role}', 'maroon')
            elif candidate.stage == 'Offer':
                log_activity(uid, f'Offer sent to {candidate.name} for {candidate.role}', 'primary')
            else:
                log_activity(
                    uid,
                    f'{candidate.name} advanced to {candidate.stage} for {candidate.role}',
                    'primary',
                )

    @action(detail=True, methods=['post'])
    def screen(self, request, pk=None):
        """Runs AI resume screening for this candidate against their linked
        requisition's requirements (see recruit/ai_screening.py — a
        heuristic scorer today, drop-in replaceable with a real LLM call
        later)."""
        candidate = self.get_object()
        requisition = candidate.requisition
        score, notes = score_candidate(
            candidate.resume_text,
            requisition.title if requisition else '',
            requisition.requirements if requisition else '',
        )
        candidate.ai_score = score
        candidate.ai_score_notes = notes
        candidate.save(update_fields=['ai_score', 'ai_score_notes', 'updated_at'])
        return Response(CandidateSerializer(candidate, context={'request': request}).data)


class CandidatePortalView(APIView):
    """The public, no-login status page a candidate sees at their own
    portal link (frontend: /portal/[token]) — looked up by the unguessable
    portal_token, not by owner, since the candidate isn't an authenticated
    user of this system at all. Deliberately returns only
    CandidatePortalSerializer's narrow, non-sensitive field set."""

    permission_classes = [AllowAny]

    def get(self, request, token):
        candidate = get_object_or_404(Candidate, portal_token=token)
        return Response(CandidatePortalSerializer(candidate).data)


class OfferLetterViewSet(CsvImportExportMixin, OwnedModelViewSet):
    queryset = OfferLetter.objects.select_related('candidate').all()
    serializer_class = OfferLetterSerializer

    csv_filename = 'offer-letters'
    csv_activity_label = 'offer letters'
    csv_import_fields = {
        'candidate': 'Candidate (name or email)',
        'job_title': 'Job title',
        'salary': 'Salary',
        'start_date': 'Start date (YYYY-MM-DD)',
        'body': 'Letter body',
        'status': 'Status (Draft, Sent, Signed, or Declined)',
    }
    csv_required_fields = ['candidate', 'job_title', 'body']
    csv_field_parsers = {'candidate': _resolve_candidate}
    csv_export_header = ['Candidate', 'Job title', 'Salary', 'Start date', 'Status', 'Sent at', 'Signed at']
    csv_sample_row = [
        'Jamie Chen', 'QA Engineer', '75000', '2026-09-01',
        'We are pleased to offer you the QA Engineer position at Acme Corp...', 'Draft',
    ]

    def csv_export_row(self, o):
        return [o.candidate.name, o.job_title, o.salary, o.start_date, o.status, o.sent_at, o.signed_at]

    def perform_create(self, serializer):
        offer = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'Offer letter drafted for {offer.candidate.name}', 'neutral')

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        offer = serializer.save()
        uid = owner_scope_id(self.request)
        if offer.status != previous_status:
            if offer.status == 'Sent' and not offer.sent_at:
                offer.sent_at = timezone.now()
                offer.save(update_fields=['sent_at'])
                log_activity(uid, f'Offer letter sent to {offer.candidate.name}', 'primary')
            elif offer.status == 'Signed' and not offer.signed_at:
                offer.signed_at = timezone.now()
                offer.save(update_fields=['signed_at'])
                log_activity(uid, f'{offer.candidate.name} signed their offer letter', 'primary')
            elif offer.status == 'Declined':
                log_activity(uid, f'{offer.candidate.name} declined their offer letter', 'maroon')


class BackgroundCheckViewSet(CsvImportExportMixin, OwnedModelViewSet):
    queryset = BackgroundCheck.objects.select_related('candidate').all()
    serializer_class = BackgroundCheckSerializer

    csv_filename = 'background-checks'
    csv_activity_label = 'background checks'
    csv_import_fields = {
        'candidate': 'Candidate (name or email)',
        'check_type': 'Screening type (Education, Employment, Criminal, or EEC)',
        'status': 'Status (Pending, In Progress, Cleared, or Flagged)',
        'notes': 'Notes',
    }
    csv_required_fields = ['candidate', 'check_type']
    csv_field_parsers = {'candidate': _resolve_candidate}
    csv_export_header = ['Candidate', 'Screening type', 'Status', 'Initiated', 'Completed', 'Notes']
    csv_sample_row = ['Jamie Chen', 'Education', 'Pending', '']

    def csv_export_row(self, b):
        return [b.candidate.name, b.get_check_type_display(), b.status, b.initiated_at, b.completed_at, b.notes]

    def perform_create(self, serializer):
        check = serializer.save(owner_id=owner_scope_id(self.request), initiated_at=timezone.now())
        log_activity(
            owner_scope_id(self.request), f'{check.get_check_type_display()} check started for {check.candidate.name}', 'neutral'
        )

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        check = serializer.save()
        if check.status != previous_status and check.status in ('Cleared', 'Flagged') and not check.completed_at:
            check.completed_at = timezone.now()
            check.save(update_fields=['completed_at'])
            tone = 'primary' if check.status == 'Cleared' else 'maroon'
            log_activity(owner_scope_id(self.request), f'{check.candidate.name} background check: {check.status}', tone)


class OnboardingViewSet(OwnedModelViewSet):
    queryset = Onboarding.objects.select_related('candidate').prefetch_related('tasks').all()
    serializer_class = OnboardingSerializer

    def perform_create(self, serializer):
        onboarding = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'Onboarding started for {onboarding.candidate.name}', 'neutral')


class OnboardingTaskViewSet(viewsets.ModelViewSet):
    """No IsOwner here — OnboardingTask has no `owner` field of its own
    (only its parent Onboarding does), so that permission's `obj.owner_id`
    check doesn't apply. Ownership is enforced entirely by scoping the
    queryset to the parent's owner, same "404 not 403" effect. IT Manager
    gets a narrow view+update slice of just the Device Assignment rows
    ("device tasks")."""

    queryset = OnboardingTask.objects.select_related('onboarding').all()
    serializer_class = OnboardingTaskSerializer
    permission_classes = [IsAuthenticated, IsHR | IsRecruiter | IsITManagerTaskAccess]

    def get_queryset(self):
        qs = self.queryset.filter(onboarding__owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'IT Manager'):
            qs = qs.filter(category='Device Assignment')
        return qs


class OffboardingViewSet(OwnedModelViewSet):
    queryset = Offboarding.objects.select_related('candidate').prefetch_related('tasks').all()
    serializer_class = OffboardingSerializer

    def perform_create(self, serializer):
        offboarding = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'Offboarding started for {offboarding.candidate.name}', 'amber')


class OffboardingTaskViewSet(viewsets.ModelViewSet):
    """Same reasoning as OnboardingTaskViewSet — no IsOwner, ownership comes
    from scoping the queryset to the parent Offboarding's owner. IT Manager
    gets a narrow view+update slice of just the Hardware Clearance rows."""

    queryset = OffboardingTask.objects.select_related('offboarding').all()
    serializer_class = OffboardingTaskSerializer
    permission_classes = [IsAuthenticated, IsHR | IsRecruiter | IsITManagerTaskAccess]

    def get_queryset(self):
        qs = self.queryset.filter(offboarding__owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'IT Manager'):
            qs = qs.filter(category='Hardware Clearance')
        return qs


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

    permission_classes = [IsAuthenticated, IsHR | IsRecruiter]

    def get(self, request):
        uid = owner_scope_id(request)
        candidates = Candidate.objects.filter(owner_id=uid)
        requisitions = Requisition.objects.filter(owner_id=uid)
        payroll_runs = PayrollRun.objects.filter(owner_id=uid)

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
            for item in ActivityLog.objects.filter(owner_id=uid)[:6]
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
