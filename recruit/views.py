import uuid
from datetime import timedelta

from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access_matrix import has_any_reports, matrix_permission, scoped_queryset
from core.activity import log_activity
from core.models import ActivityLog
from core.csv_io import CsvImportExportMixin, resolve_related
from core.permissions import (
    IsAuditorReadOnly,
    IsDepartmentHeadReadOnly,
    IsDepartmentHeadRequisitionAccess,
    IsFinanceAdminReadOnly,
    IsHR,
    IsITManagerTaskAccess,
    IsOwner,
    IsRecruiter,
    is_hr_or_legacy,
    _role_is,
    owner_scope_id,
)
from payroll_benefits.models import PayrollRun

from .ai_screening import score_candidate
from .permissions import (
    IsFinanceAdminHardwareClearanceReadOnly,
    IsITManagerAccessStatusAccess,
    IsSelfOnboardingTaskAccess,
    _my_candidate_id,
    manager_broad_access,
    manager_candidate_access,
    manager_candidate_ids,
)
from .models import (
    BackgroundCheck,
    Candidate,
    Client,
    Offboarding,
    OffboardingTask,
    OfferLetter,
    OfferLetterTemplate,
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
    OfferLetterTemplateSerializer,
    OnboardingSerializer,
    OnboardingTaskSerializer,
    RequisitionSerializer,
)

def _escape_ics(text):
    return text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


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
    Recruit access at all.

    Control Hierarchy Matrix (Client row): SA/HRA=RWA, FA=R, AUD=R,
    REC=RW* ("assigned clients only"). Client has no "assigned clients"
    concept to scope Recruiter by — Recruiter already has full org-wide
    access via IsRecruiter, which is a superset of RW*, so that's left as
    is (documented over-grant, same approximation the migration brief
    sanctions for this exact row) rather than blocking on a new assignment
    feature. FA/AUD get plain org-wide read below; get_queryset needs no
    change since OwnedModelViewSet already returns the full tenant-scoped
    list to anyone permission_classes lets through."""

    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsRecruiter | IsDepartmentHeadReadOnly | matrix_permission(fa='R', aud='R'),
    ]

    csv_filename = 'clients'
    csv_activity_label = 'clients'
    csv_import_fields = {
        'name': 'Name',
        'industry': 'Industry',
        'contact_name': 'Contact name',
        'contact_email': 'Contact email',
        'contact_number': 'Contact number',
        'status': 'Status (Active, Prospect, or At risk)',
    }
    csv_required_fields = ['name']
    csv_export_header = ['Name', 'Industry', 'Contact name', 'Contact email', 'Contact number', 'Status']
    csv_sample_row = ['Acme Corp', 'Manufacturing', 'Jordan Lee', 'jordan@acme.com', '+1 555-0100', 'Active']

    def get_csv_export_queryset(self):
        return self.get_queryset().order_by('name')

    def csv_export_row(self, c):
        return [c.name, c.industry, c.contact_name, c.contact_email, c.contact_number, c.status]

    def perform_create(self, serializer):
        client = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'New client added: {client.name}', 'neutral')


class RequisitionViewSet(CsvImportExportMixin, OwnedModelViewSet):
    """Department Head may also view every requisition and create new ones
    ("request for recruit") on top of HR/Admin/Recruiter's full access —
    never update/delete an existing one.

    Control Hierarchy Matrix (Job Openings row): SA/HRA=RWA, FA=R, AUD=R,
    MGR=R*/A* ("requisition goes to Manager for approval before HR
    Admin/Recruiter posts live"), REC=RW* (already exceeded by IsRecruiter).
    Requisition.hiring_manager is a free-text label, not an FK to a specific
    Employee/manager, and the model has no "pending manager approval"
    status choice at all (STATUS_CHOICES is Open/Interviewing/Offer
    stage/On hold/Filled) — so the exact "goes to Manager before posting"
    workflow gate can't be enforced without a new status value or an
    assignment field. Approximated, like the Client row, as read+approve
    access for any login that is actually a manager, tenant-wide rather
    than scoped to "their" requisitions specifically; get_queryset needs no
    override since OwnedModelViewSet's plain owner-scoped list already
    covers this approximation."""

    queryset = Requisition.objects.select_related('client').all()
    serializer_class = RequisitionSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner
        | IsRecruiter
        | IsDepartmentHeadRequisitionAccess
        | matrix_permission(fa='R', aud='R')
        | manager_broad_access((*SAFE_METHODS, 'PUT', 'PATCH')),
    ]

    csv_filename = 'job-openings'
    csv_activity_label = 'job openings'
    csv_import_fields = {
        'client': 'Client (exact name)',
        'title': 'Role title',
        'recruiter': 'Recruiter',
        'priority': 'Priority (High, Medium, or Low)',
        'status': 'Status (Open, Interviewing, Offer stage, On hold, or Filled)',
        'requirements': 'Requirements',
        'salary_min': 'Salary min (USD)',
        'salary_max': 'Salary max (USD)',
        'location': 'Location',
        'employment_type': 'Employment type (Full-time, Part-time, Contract, or Temporary)',
        'headcount': 'Headcount',
        'description': 'Description',
        'hiring_manager': 'Hiring manager',
    }
    csv_required_fields = ['client', 'title']
    csv_field_parsers = {'client': _resolve_client}
    csv_export_header = [
        'Client', 'Role title', 'Recruiter', 'Priority', 'Status', 'Salary min', 'Salary max', 'Location',
        'Employment type', 'Headcount', 'Hiring manager', 'Posted', 'Candidates',
    ]
    csv_sample_row = [
        'Acme Corp', 'Senior QA Engineer', 'Alex Rivera', 'High', 'Open', 'Python, React, 3+ years experience',
        '90000', '120000', 'Remote (US)', 'Full-time', '1', 'Own the QA strategy for our flagship product.',
        'Taylor Morgan',
    ]

    def csv_export_row(self, r):
        return [
            r.client.name, r.title, r.recruiter, r.priority, r.status, r.salary_min, r.salary_max, r.location,
            r.employment_type, r.headcount, r.hiring_manager, r.posted_at, r.candidates.count(),
        ]

    def perform_create(self, serializer):
        requisition = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(
            owner_scope_id(self.request),
            f'New requisition opened: {requisition.title} at {requisition.client.name}',
            'neutral',
        )

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        requisition = serializer.save()
        if requisition.status != previous_status:
            log_activity(
                owner_scope_id(self.request),
                f'{requisition.title} moved to {requisition.status}',
                'primary' if requisition.status in ('Offer stage', 'Filled') else 'neutral',
            )


class CandidateViewSet(CsvImportExportMixin, OwnedModelViewSet):
    """Backs three Control Hierarchy Matrix rows on the same model/viewset —
    Candidates (SA/HRA=RWA, AUD=R, MGR=R*, REC=RW), Resume Pool ("just
    candidates viewed through this lens" per the model docstring; AUD=R,
    MGR='-', REC=RW), and AI Resume Screening (the `screen` action below;
    AUD=R, MGR=R*, REC=RW). REC is already exceeded org-wide via
    IsRecruiter on all three. Taking the union across the three rows (same
    reasoning as People's shared AttendanceRecord viewset): AUD=R and
    MGR=R* stand for the whole viewset — Resume Pool's MGR='-' is a minor,
    accepted over-grant of the same kind. MGR is approximated tenant-wide
    (manager_broad_access) since Candidate has no manager-assignment FK —
    see RequisitionViewSet's docstring for the same underlying gap."""

    queryset = Candidate.objects.select_related('client', 'requisition').all()
    serializer_class = CandidateSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsRecruiter | matrix_permission(aud='R') | manager_broad_access(SAFE_METHODS),
    ]

    csv_filename = 'candidates'
    csv_activity_label = 'candidates'
    csv_import_fields = {
        'name': 'Name',
        'role': 'Current position',
        'email': 'Email',
        'phone': 'Phone',
        'country': 'Country',
        'city': 'City of application',
        'stage': 'Stage (Sourced, Interview, Offer, Placed, or Rejected)',
        'source': 'Source (LinkedIn, Referral, Job Board, Sourced, or Other)',
        'current_salary': 'Current salary (USD)',
        'applied_at': 'Applied at (YYYY-MM-DD)',
    }
    csv_required_fields = ['name', 'role']
    csv_export_header = ['Name', 'Role', 'Email', 'Phone', 'Country', 'City', 'Stage', 'Source', 'Applied at', 'AI score']
    csv_sample_row = [
        'Jamie Chen', 'QA Engineer', 'jamie.chen@example.com', '+1 555-0100', 'United States', 'Austin',
        'Sourced', 'LinkedIn', '75000', '2026-08-01',
    ]

    def get_csv_export_queryset(self):
        return self.get_queryset().order_by('name')

    def csv_export_row(self, c):
        return [c.name, c.role, c.email, c.phone, c.country, c.city, c.stage, c.source, c.applied_at, c.ai_score]

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
        requisition's requirements — real AI via ai_core if the org has
        connected a provider, otherwise a 409 (the frontend's AiFeatureGate
        is the primary UX guard; this is defense-in-depth against a stale
        client or a direct API call bypassing it)."""
        candidate = self.get_object()
        requisition = candidate.requisition
        result = score_candidate(
            owner_scope_id(request),
            candidate.resume_text,
            requisition.title if requisition else '',
            requisition.requirements if requisition else '',
        )
        if not result['configured']:
            return Response(
                {'detail': 'No AI provider connected for resume screening.', 'code': 'ai_not_configured'},
                status=409,
            )
        candidate.ai_score = result['score']
        candidate.ai_score_notes = result['notes']
        candidate.ai_score_strengths = result['strengths']
        candidate.ai_score_gaps = result['gaps']
        candidate.save(
            update_fields=['ai_score', 'ai_score_notes', 'ai_score_strengths', 'ai_score_gaps', 'updated_at']
        )
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


class OfferLetterTemplateViewSet(OwnedModelViewSet):
    queryset = OfferLetterTemplate.objects.select_related('client').all()
    serializer_class = OfferLetterTemplateSerializer

    def perform_create(self, serializer):
        template = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(
            owner_scope_id(self.request),
            f'Offer letter template saved: {template.role_title} at {template.client.name}',
            'neutral',
        )


class OfferLetterViewSet(CsvImportExportMixin, OwnedModelViewSet):
    """Control Hierarchy Matrix (Digital Offer Letters row): SA=RWA,
    HRA=RW (already exceeded by IsOwner's full HR access), FA=R, AUD=R,
    MGR=A* ("manager approves before send" — approximated tenant-wide,
    same hiring-manager-FK gap as RequisitionViewSet), REC=RW (already
    exceeded by IsRecruiter)."""

    queryset = OfferLetter.objects.select_related('candidate').all()
    serializer_class = OfferLetterSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner
        | IsRecruiter
        | matrix_permission(fa='R', aud='R')
        | manager_broad_access((*SAFE_METHODS, 'PUT', 'PATCH')),
    ]

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
    """Control Hierarchy Matrix (Background Check Integration row): SA=RWA,
    HRA=RW (already exceeded), AUD=R, REC=RW (already exceeded), EMP=R*
    ("candidates/employees see own consent status only"), CON='-' (no
    access). "Own" for EMP is resolved via _my_candidate_id
    (people.Employee.source_candidate) since this model is keyed by
    Candidate, not Employee — see recruit.permissions module docstring."""

    queryset = BackgroundCheck.objects.select_related('candidate').all()
    serializer_class = BackgroundCheckSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner
        | IsRecruiter
        | matrix_permission(self_scope_field='candidate_id', self_id_getter=_my_candidate_id, aud='R', emp='R*'),
    ]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request) or _role_is(self.request, 'Recruiter') or _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(
            self.request, qs, self_scope_field='candidate_id', self_id_getter=_my_candidate_id, emp='R*'
        )

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
    """Control Hierarchy Matrix (Onboarding > Overview row): SA/HRA=RWA,
    ITA=R, AUD=R, MGR=R*, REC=R (already exceeded by IsRecruiter), EMP=R*,
    CON=R* ("new hire/Contractor see own checklist read-only"). "Own" for
    EMP/CON is resolved via _my_candidate_id since Onboarding is keyed by
    Candidate, not Employee. MGR's "own team" here is a real reverse lookup
    (manager_candidate_access/manager_candidate_ids) through
    people.Employee.source_candidate — unlike Requisition/Candidate/
    OfferLetter, a hired candidate really does have a resolvable
    Employee + manager chain."""

    queryset = Onboarding.objects.select_related('candidate').prefetch_related('tasks').all()
    serializer_class = OnboardingSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner
        | IsRecruiter
        | matrix_permission(
            self_scope_field='candidate_id', self_id_getter=_my_candidate_id, ita='R', aud='R', emp='R*', con='R*'
        )
        | manager_candidate_access(candidate_field='candidate_id', methods=SAFE_METHODS),
    ]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if (
            is_hr_or_legacy(self.request)
            or _role_is(self.request, 'Recruiter')
            or _role_is(self.request, 'IT Manager')
            or _role_is(self.request, 'Auditor')
        ):
            return qs
        if has_any_reports(self.request):
            return qs.filter(candidate_id__in=manager_candidate_ids(self.request))
        return scoped_queryset(
            self.request, qs, self_scope_field='candidate_id', self_id_getter=_my_candidate_id, emp='R*', con='R*'
        )

    def perform_create(self, serializer):
        onboarding = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'Onboarding started for {onboarding.candidate.name}', 'neutral')


class OnboardingTaskViewSet(viewsets.ModelViewSet):
    """No IsOwner here — OnboardingTask has no `owner` field of its own
    (only its parent Onboarding does), so that permission's `obj.owner_id`
    check doesn't apply. Ownership is enforced entirely by scoping the
    queryset to the parent's owner, same "404 not 403" effect. IT Manager
    gets a narrow view+update slice of just the Device Assignment rows
    ("device tasks").

    This one viewset also backs the Control Hierarchy Matrix's Joining
    Documentation/Orientation/Training Plan/Portal Access/Probation
    Evaluation/Device Assignment rows (all OnboardingTask, split only by
    `category`, same shared-model situation as People's Attendance rows).
    AUD=R across every category (plain org-wide read, added below). MGR is
    real team-scoped (own former report's checklist) only for Orientation/
    Training Plan (R*) and Probation Evaluation (RW*/A*) — every other
    category has MGR='-'. EMP/CON's own-checklist access differs by
    category (W*/R*/RW*/none) and is handled by IsSelfOnboardingTaskAccess
    (see recruit/permissions.py) rather than the generic engine."""

    queryset = OnboardingTask.objects.select_related('onboarding').all()
    serializer_class = OnboardingTaskSerializer
    permission_classes = [
        IsAuthenticated,
        IsHR
        | IsRecruiter
        | IsITManagerTaskAccess
        | matrix_permission(owner_getter=lambda obj: obj.onboarding.owner_id, aud='R')
        | manager_candidate_access(
            candidate_field='onboarding__candidate_id', methods=SAFE_METHODS, categories={'Orientation', 'Training Plan'}
        )
        | manager_candidate_access(
            candidate_field='onboarding__candidate_id',
            methods=(*SAFE_METHODS, 'PUT', 'PATCH'),
            categories={'Probation Evaluation'},
        )
        | IsSelfOnboardingTaskAccess,
    ]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = self.queryset.filter(onboarding__owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request) or _role_is(self.request, 'Recruiter') or _role_is(self.request, 'Auditor'):
            return qs
        if _role_is(self.request, 'IT Manager'):
            return qs.filter(category='Device Assignment')
        if has_any_reports(self.request):
            return qs.filter(
                onboarding__candidate_id__in=manager_candidate_ids(self.request),
                category__in=['Orientation', 'Training Plan', 'Probation Evaluation'],
            )
        my_candidate_id = _my_candidate_id(self.request)
        if not my_candidate_id:
            return qs.none()
        profile = getattr(self.request.user, 'profile', None)
        categories = list(
            IsSelfOnboardingTaskAccess.EMP_CODES
            if (profile and profile.role == 'Employee')
            else IsSelfOnboardingTaskAccess.CON_CODES
        )
        return qs.filter(onboarding__candidate_id=my_candidate_id, category__in=categories)

    @action(detail=True, methods=['get'])
    def ics(self, request, pk=None):
        """A downloadable .ics calendar invite for this task — used by
        Orientation tasks ("send a calendar invite"). No Google Calendar
        OAuth integration exists (nobody has provisioned credentials for
        it), so this generates a standard calendar file instead, which
        opens directly in Google Calendar/Outlook/Apple Calendar without
        needing any API key."""
        task = self.get_object()
        event_date = task.due_date or timezone.now().date()
        uid = f'{uuid.uuid4()}@pulse-hr'
        ics_body = (
            'BEGIN:VCALENDAR\r\n'
            'VERSION:2.0\r\n'
            'PRODID:-//Pulse//Onboarding//EN\r\n'
            'BEGIN:VEVENT\r\n'
            f'UID:{uid}\r\n'
            f'DTSTAMP:{timezone.now().strftime("%Y%m%dT%H%M%SZ")}\r\n'
            f'DTSTART;VALUE=DATE:{event_date.strftime("%Y%m%d")}\r\n'
            f'SUMMARY:{_escape_ics(task.title)}\r\n'
            f'DESCRIPTION:{_escape_ics(task.notes)}\r\n'
            'END:VEVENT\r\n'
            'END:VCALENDAR\r\n'
        )
        response = HttpResponse(ics_body, content_type='text/calendar')
        response['Content-Disposition'] = f'attachment; filename="{task.title[:50]}.ics"'
        return response


class OffboardingViewSet(OwnedModelViewSet):
    """Backs two Control Hierarchy Matrix rows on the same model — Overview
    (SA/HRA=RWA, ITA=R, AUD=R, MGR=R*) and Rehire & Alumni Pool (same
    model's rehire_* fields; SA/HRA=RWA, AUD=R, MGR=A*, REC=R — already
    exceeded by IsRecruiter). Taking the union for MGR (R* + A* -> real
    read+write access to their own former report's record, via the same
    reverse-lookup team-scoping as OnboardingViewSet) — same reasoning as
    the shared-model rows elsewhere. EMP/CON are '-' (no access) on every
    Offboarding-related row, so there's nothing to add for them anywhere in
    this module."""

    queryset = Offboarding.objects.select_related('candidate').prefetch_related('tasks').all()
    serializer_class = OffboardingSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner
        | IsRecruiter
        | matrix_permission(ita='R', aud='R')
        | manager_candidate_access(candidate_field='candidate_id', methods=(*SAFE_METHODS, 'PUT', 'PATCH')),
    ]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if (
            is_hr_or_legacy(self.request)
            or _role_is(self.request, 'Recruiter')
            or _role_is(self.request, 'IT Manager')
            or _role_is(self.request, 'Auditor')
        ):
            return qs
        if has_any_reports(self.request):
            return qs.filter(candidate_id__in=manager_candidate_ids(self.request))
        return qs.none()

    def perform_create(self, serializer):
        offboarding = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'Offboarding started for {offboarding.candidate.name}', 'amber')


class OffboardingTaskViewSet(viewsets.ModelViewSet):
    """Same reasoning as OnboardingTaskViewSet — no IsOwner, ownership comes
    from scoping the queryset to the parent Offboarding's owner. IT Manager
    gets a narrow view+update slice of just the Hardware Clearance rows
    (pre-existing) plus, per the Control Hierarchy Matrix, Access Status now
    too (RWA there) — core.permissions' shared IsITManagerTaskAccess only
    covers Device Assignment/Hardware Clearance, so
    IsITManagerAccessStatusAccess supplements it for the new category
    rather than editing that shared class. AUD=R across every category
    (added below, plain org-wide). Finance Admin gets a narrow read-only
    slice of Hardware Clearance specifically ("sees asset value/write-off
    impact"), unlike every other Offboarding row where FA='-'. EMP/CON are
    '-' everywhere in this viewset — no self-service access to add."""

    queryset = OffboardingTask.objects.select_related('offboarding').all()
    serializer_class = OffboardingTaskSerializer
    permission_classes = [
        IsAuthenticated,
        IsHR
        | IsRecruiter
        | IsITManagerTaskAccess
        | matrix_permission(owner_getter=lambda obj: obj.offboarding.owner_id, aud='R')
        | IsITManagerAccessStatusAccess
        | IsFinanceAdminHardwareClearanceReadOnly,
    ]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = self.queryset.filter(offboarding__owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request) or _role_is(self.request, 'Recruiter') or _role_is(self.request, 'Auditor'):
            return qs
        if _role_is(self.request, 'IT Manager'):
            return qs.filter(category__in=['Access Status', 'Hardware Clearance'])
        if _role_is(self.request, 'Finance Admin'):
            return qs.filter(category='Hardware Clearance')
        return qs.none()


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


class _IsITManagerReadOnly(BasePermission):
    """Read-only aggregate access to Recruit's dashboard summary for IT
    Manager — their real matrix grant here is narrow (a handful of
    onboarding/offboarding device/access categories, not the whole
    module), but the module hub page they can now reach needs this
    endpoint to render at all; same "secondary role gets broad read on
    the aggregate view" precedent already used here for Finance Admin/
    Auditor/Department Head."""

    def has_permission(self, request, view):
        return _role_is(request, 'IT Manager') and request.method in SAFE_METHODS


class DashboardSummaryView(APIView):
    """Recruit's overview/analytics numbers, computed live from the
    user's own data — nothing here is stored/cached. "Revenue this month"
    reads from payroll_benefits.PayrollRun since placement-fee revenue is
    tracked as payroll, not as a Recruit-owned figure.

    Control Hierarchy Matrix (Analytics > Recruiting dashboard row):
    SA/HRA=RWA, FA=R, AUD=R, MGR=R*, REC=R* (already exceeded by
    IsRecruiter). This is a plain APIView with no per-object checks, so
    matrix_permission's has_permission-level MGR handling (has_any_reports)
    is all that applies — there's no get_object() here to scope further.
    The KPIs themselves stay tenant-wide for FA/AUD/MGR alike (not narrowed
    to "own team/requirements only" as the matrix intends for MGR) since
    that would mean re-deriving every aggregate from a "my team's
    candidates/requisitions" queryset with no clean way to define that set
    (see Requisition/Candidate's own MGR-scoping notes) — the same
    limitation the People dashboard's own summary view already accepts for
    Department Head/Manager-style scoping."""

    permission_classes = [
        IsAuthenticated,
        IsHR
        | IsRecruiter
        | IsFinanceAdminReadOnly
        | IsAuditorReadOnly
        | IsDepartmentHeadReadOnly
        | _IsITManagerReadOnly
        | matrix_permission(mgr='R'),
    ]

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
