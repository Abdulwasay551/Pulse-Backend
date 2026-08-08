from datetime import timedelta

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.csv_io import csv_response, parse_csv_upload, row_to_record, suggest_mapping
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

CLIENT_IMPORT_FIELDS = {
    'name': 'Name',
    'industry': 'Industry',
    'contact_name': 'Contact name',
    'contact_email': 'Contact email',
    'status': 'Status',
}
CLIENT_REQUIRED_FIELDS = ['name']

CANDIDATE_IMPORT_FIELDS = {
    'name': 'Name',
    'role': 'Role',
    'email': 'Email',
    'phone': 'Phone',
    'stage': 'Stage',
    'source': 'Source',
    'applied_at': 'Applied at',
}
CANDIDATE_REQUIRED_FIELDS = ['name', 'role']


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


class ClientViewSet(OwnedModelViewSet):
    """Department Head gets read-only access on top of HR/Admin/Recruiter's
    full access — needed to populate the client picker when they create a
    Requisition ("request for recruit"), even though they otherwise have no
    Recruit access at all."""

    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsRecruiter | IsDepartmentHeadReadOnly]

    def perform_create(self, serializer):
        client = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'New client added: {client.name}', 'neutral')

    @action(detail=False, methods=['get'])
    def export(self, request):
        clients = self.get_queryset().order_by('name')
        header = ['Name', 'Industry', 'Contact name', 'Contact email', 'Status']
        rows = [[c.name, c.industry, c.contact_name, c.contact_email, c.status] for c in clients]
        return csv_response('clients.csv', header, rows)

    @action(detail=False, methods=['get'], url_path='import/template')
    def import_template(self, request):
        """A blank CSV with just the header row, so HR can see the expected
        columns before uploading a real file — separate from `export`,
        which dumps actual data."""
        return csv_response('clients-import-template.csv', list(CLIENT_IMPORT_FIELDS.values()), [])

    @action(detail=False, methods=['post'], url_path='import/preview', parser_classes=[MultiPartParser, FormParser])
    def import_preview(self, request):
        return _import_preview(request, CLIENT_IMPORT_FIELDS)

    @action(detail=False, methods=['post'], url_path='import/commit', parser_classes=[JSONParser])
    def import_commit(self, request):
        return _import_commit(
            request,
            serializer_class=ClientSerializer,
            required_fields=CLIENT_REQUIRED_FIELDS,
            valid_fields=set(CLIENT_IMPORT_FIELDS),
            on_created=lambda user, count: log_activity(
                user, f'Imported {count} client{"s" if count != 1 else ""} from CSV', 'neutral'
            ),
        )


class RequisitionViewSet(OwnedModelViewSet):
    """Department Head may also view every requisition and create new ones
    ("request for recruit") on top of HR/Admin/Recruiter's full access —
    never update/delete an existing one."""

    queryset = Requisition.objects.select_related('client').all()
    serializer_class = RequisitionSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsRecruiter | IsDepartmentHeadRequisitionAccess]

    def perform_create(self, serializer):
        requisition = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(
            owner_scope_id(self.request),
            f'New requisition opened: {requisition.title} at {requisition.client.name}',
            'neutral',
        )


class CandidateViewSet(OwnedModelViewSet):
    queryset = Candidate.objects.select_related('client', 'requisition').all()
    serializer_class = CandidateSerializer

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

    @action(detail=False, methods=['get'])
    def export(self, request):
        candidates = self.get_queryset().order_by('name')
        header = ['Name', 'Role', 'Email', 'Phone', 'Stage', 'Source', 'Applied at', 'AI score']
        rows = [
            [c.name, c.role, c.email, c.phone, c.stage, c.source, c.applied_at, c.ai_score]
            for c in candidates
        ]
        return csv_response('candidates.csv', header, rows)

    @action(detail=False, methods=['get'], url_path='import/template')
    def import_template(self, request):
        return csv_response('candidates-import-template.csv', list(CANDIDATE_IMPORT_FIELDS.values()), [])

    @action(detail=False, methods=['post'], url_path='import/preview', parser_classes=[MultiPartParser, FormParser])
    def import_preview(self, request):
        return _import_preview(request, CANDIDATE_IMPORT_FIELDS)

    @action(detail=False, methods=['post'], url_path='import/commit', parser_classes=[JSONParser])
    def import_commit(self, request):
        return _import_commit(
            request,
            serializer_class=CandidateSerializer,
            required_fields=CANDIDATE_REQUIRED_FIELDS,
            valid_fields=set(CANDIDATE_IMPORT_FIELDS),
            on_created=lambda user, count: log_activity(
                user, f'Imported {count} candidate{"s" if count != 1 else ""} from CSV', 'neutral'
            ),
        )


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


class OfferLetterViewSet(OwnedModelViewSet):
    queryset = OfferLetter.objects.select_related('candidate').all()
    serializer_class = OfferLetterSerializer

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


class BackgroundCheckViewSet(OwnedModelViewSet):
    queryset = BackgroundCheck.objects.select_related('candidate').all()
    serializer_class = BackgroundCheckSerializer

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


def _import_preview(request, field_labels):
    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        columns, rows = parse_csv_upload(upload)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            'columns': columns,
            'rows': rows,
            'row_count': len(rows),
            'suggested_mapping': suggest_mapping(columns, field_labels),
            'fields': field_labels,
        }
    )


def _import_commit(request, *, serializer_class, required_fields, valid_fields, on_created):
    columns = request.data.get('columns')
    rows = request.data.get('rows')
    mapping = request.data.get('mapping')
    if not isinstance(columns, list) or not isinstance(rows, list) or not isinstance(mapping, dict):
        return Response(
            {'detail': 'Expected {columns, rows, mapping} from the preview step.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    mapping = {k: v for k, v in mapping.items() if v in valid_fields}
    mapped_fields = set(mapping.values())
    missing_required = [f for f in required_fields if f not in mapped_fields]
    if missing_required:
        return Response(
            {'detail': f'Map a column to the required field(s): {", ".join(missing_required)}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created = 0
    errors = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        record = row_to_record(columns, row, mapping)
        # Blank optional cells shouldn't override a model default (e.g. an
        # empty "Applied at" column should still fall back to today, not
        # fail validation as an empty date string) — only pass through
        # values that were actually provided.
        record = {k: v for k, v in record.items() if v != ''}
        missing = [f for f in required_fields if not record.get(f)]
        if missing:
            errors.append(f'Row {i}: {", ".join(missing)} is required')
            continue

        serializer = serializer_class(data=record, context={'request': request})
        if not serializer.is_valid():
            first_field, first_errors = next(iter(serializer.errors.items()))
            errors.append(f'Row {i}: {first_field} — {first_errors[0]}')
            continue

        serializer.save(owner_id=owner_scope_id(request))
        created += 1

    if created:
        on_created(owner_scope_id(request), created)

    return Response({'created': created, 'errors': errors})


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
