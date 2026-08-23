from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access_matrix import is_manager_of, matrix_permission, scoped_queryset
from core.csv_io import CsvImportExportMixin, resolve_employee
from core.permissions import (
    IsAuditorReadOnly,
    IsDepartmentHeadAppraisalAccess,
    IsDepartmentHeadReadOnly,
    IsDepartmentHeadWrite,
    IsHR,
    IsOwner,
    IsRecruiter,
    _role_is,
    is_hr_or_legacy,
    owner_scope_id,
)
from people.models import Employee

from .models import (
    Appraisal,
    CareerPath,
    CompetencyRating,
    Course,
    Enrollment,
    Goal,
    RecruiterFeedback,
    SuccessionPlan,
)
from .scoring import compute_value_score
from .serializers import (
    AppraisalSerializer,
    CareerPathSerializer,
    CompetencyRatingSerializer,
    CourseSerializer,
    EnrollmentSerializer,
    GoalSerializer,
    RecruiterFeedbackSerializer,
    SuccessionPlanSerializer,
)


class OwnedTalentViewSet(viewsets.ModelViewSet):
    """Shared base — every Talent resource has its own `owner` field, so
    plain IsOwner + an owner-filtered queryset covers all of them."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class DepartmentScopedTalentViewSet(OwnedTalentViewSet):
    """Goal/CompetencyRating/CareerPath — working tools, so Department Head
    gets full create+update (no approval gate) scoped to their own
    department's employees, on top of HR/Admin's full access."""

    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
        serializer.save(owner_id=owner_scope_id(self.request))


class GoalViewSet(CsvImportExportMixin, DepartmentScopedTalentViewSet):
    queryset = Goal.objects.select_related('employee').all()
    serializer_class = GoalSerializer
    # Goal Setting & KPIs: Auditor reads org-wide; Manager gets real
    # create/update for their own team's goals; Employee gets real
    # read/write on their own (e.g. progress updates); Contractor reads
    # only their own.
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadWrite | matrix_permission(aud='R', mgr='RW*', emp='RW*', con='R*'),
    ]

    csv_filename = 'goals'
    csv_activity_label = 'goals'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'title': 'Goal title',
        'section': 'Section (e.g. "Q3 OKRs", "Onboarding")',
        'description': 'Description',
        'target_date': 'Target date (YYYY-MM-DD)',
        'status': 'Status (Not Started, In Progress, or Completed)',
        'progress': 'Progress (0-100)',
    }
    csv_required_fields = ['employee', 'title']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Title', 'Section', 'Description', 'Target date', 'Status', 'Progress']
    csv_sample_row = ['Taylor Morgan', 'Ship the Q3 roadmap', 'Q3 OKRs', 'Deliver the three headline features.', '2026-09-30', 'In Progress', '40']

    def csv_export_row(self, g):
        return [g.employee.name, g.title, g.section, g.description, g.target_date, g.status, g.progress]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_hr_or_legacy(self.request) or _role_is(self.request, 'Department Head') or _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(self.request, qs, mgr='RW*', emp='RW*', con='R*')

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role == 'Employee':
            # Self-service: can only ever set/update goals for themselves,
            # whatever `employee` was submitted.
            if not profile.employee_id:
                raise PermissionDenied('Your account has no linked employee record.')
            serializer.validated_data['employee'] = profile.employee
        elif not is_hr_or_legacy(self.request) and not _role_is(self.request, 'Department Head'):
            # Manager (dynamic capability, not a stored role) creating a
            # goal for someone on their team.
            employee = serializer.validated_data.get('employee')
            if employee and not is_manager_of(self.request, employee.id):
                raise PermissionDenied('You can only set goals for someone on your team.')
        serializer.save(owner_id=owner_scope_id(self.request))


class AppraisalViewSet(CsvImportExportMixin, OwnedTalentViewSet):
    """Department Head may create/update while drafting/submitting an
    appraisal for their own department's employees, but perform_update
    below blocks them from ever finalizing one — that stays HR/Admin-only,
    the "approval required" gate for Talent."""

    queryset = Appraisal.objects.select_related('employee').all()
    serializer_class = AppraisalSerializer
    # Performance Appraisals: Auditor reads org-wide; Manager gets
    # create/update/approve for their own team ('RW*/A*' in the matrix —
    # 'A*' alone covers both since the engine treats Approve as read+write);
    # Employee/Contractor read only their own.
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadAppraisalAccess | matrix_permission(aud='R', mgr='A*', emp='R*', con='R*'),
    ]

    csv_filename = 'appraisals'
    csv_activity_label = 'appraisals'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'period': 'Period (e.g. "2026 Annual Review")',
        'reviewer': 'Reviewer',
        'overall_rating': 'Overall rating (1-5)',
        'strengths': 'Strengths',
        'areas_for_improvement': 'Areas for improvement',
        'status': 'Status (Draft, Submitted, or Finalized)',
    }
    csv_required_fields = ['employee', 'period', 'overall_rating']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Period', 'Reviewer', 'Overall rating', 'Status']
    csv_sample_row = [
        'Taylor Morgan', '2026 Annual Review', 'Jordan Ellis', '4',
        'Strong technical execution and mentorship.', 'Room to delegate more.', 'Draft',
    ]

    def csv_export_row(self, a):
        return [a.employee.name, a.period, a.reviewer, a.overall_rating, a.status]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(self.request, qs, mgr='A*', emp='R*', con='R*')

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
            if serializer.validated_data.get('status') == 'Finalized':
                raise PermissionDenied('Only HR or an Admin can finalize an appraisal.')
        elif not is_hr_or_legacy(self.request) and not _role_is(self.request, 'Auditor'):
            # Manager (dynamic capability) creating/drafting an appraisal
            # for someone on their team.
            employee = serializer.validated_data.get('employee')
            if employee and not is_manager_of(self.request, employee.id):
                raise PermissionDenied('You can only create an appraisal for someone on your team.')
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        new_status = serializer.validated_data.get('status', serializer.instance.status)
        if new_status == 'Finalized' and _role_is(self.request, 'Department Head'):
            raise PermissionDenied('Only HR or an Admin can finalize an appraisal.')
        serializer.save()


class CompetencyRatingViewSet(CsvImportExportMixin, DepartmentScopedTalentViewSet):
    """Backs both "Competency Mapping of Employees" (Goals & Appraisal) and
    "Skills & Competency Mapping" (Learning & Growth) — identical codes on
    both matrix rows: Auditor org-wide read, Manager/Employee read-only
    scoped to team/own record, Contractor no access."""

    queryset = CompetencyRating.objects.select_related('employee').all()
    serializer_class = CompetencyRatingSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadWrite | matrix_permission(aud='R', mgr='R*', emp='R*'),
    ]

    csv_filename = 'competency-ratings'
    csv_activity_label = 'competency ratings'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'competency': 'Competency',
        'level': 'Level (1-5)',
        'notes': 'Notes',
    }
    csv_required_fields = ['employee', 'competency']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Competency', 'Level', 'Notes']
    csv_sample_row = ['Taylor Morgan', 'System design', '4', '']

    def csv_export_row(self, c):
        return [c.employee.name, c.competency, c.level, c.notes]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_hr_or_legacy(self.request) or _role_is(self.request, 'Department Head') or _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(self.request, qs, mgr='R*', emp='R*')


class CourseViewSet(CsvImportExportMixin, OwnedTalentViewSet):
    """The training catalog itself has no per-employee ownership, so every
    role the matrix grants Training & LMS access to just reads the whole
    catalog (no self-scoping applies here — that's Enrollment's job)."""

    queryset = Course.objects.prefetch_related('enrollments').all()
    serializer_class = CourseSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner | matrix_permission(aud='R', mgr='R', emp='R', con='R'),
    ]

    csv_filename = 'courses'
    csv_activity_label = 'courses'
    csv_import_fields = {
        'title': 'Title',
        'description': 'Description',
        'duration_hours': 'Duration (hours)',
        'link': 'Course link (Google Meet, Udemy Business, LinkedIn Learning, etc.)',
        'is_active': 'Active (True or False)',
    }
    csv_required_fields = ['title']
    csv_export_header = ['Title', 'Description', 'Duration (hours)', 'Link', 'Active', 'Enrollments']
    csv_sample_row = ['Leadership Fundamentals', 'An intro to people-management skills.', '6', 'https://www.udemy.com/course/leadership-fundamentals/', 'True']

    def csv_export_row(self, c):
        return [c.title, c.description, c.duration_hours, c.link, c.is_active, c.enrollments.count()]


class EnrollmentViewSet(viewsets.ModelViewSet):
    """No IsOwner — Enrollment has no `owner` field of its own, scoped via
    its parent Course's owner, same reasoning as EmployeeDocument. Training
    & LMS: Auditor reads org-wide; Manager reads their team's enrollments
    (unstarred 'R' in the matrix, but MGR is always team-scoped regardless
    — see access_matrix); Employee/Contractor get real read/write on their
    own enrollment (progress/completion updates)."""

    queryset = Enrollment.objects.select_related('employee', 'course').all()
    serializer_class = EnrollmentSerializer
    permission_classes = [
        IsAuthenticated,
        IsHR
        | matrix_permission(owner_getter=lambda obj: obj.course.owner_id, aud='R', mgr='R', emp='RW*', con='RW*'),
    ]

    def get_queryset(self):
        qs = self.queryset.filter(course__owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request) or _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(self.request, qs, mgr='R', emp='RW*', con='RW*')

    def perform_create(self, serializer):
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role in ('Employee', 'Contractor'):
            # Self-service: can only ever enroll/update progress for
            # themselves, whatever `employee` was submitted.
            if not profile.employee_id:
                raise PermissionDenied('Your account has no linked employee record.')
            serializer.validated_data['employee'] = profile.employee
        serializer.save()


class CareerPathViewSet(CsvImportExportMixin, DepartmentScopedTalentViewSet):
    queryset = CareerPath.objects.select_related('employee').all()
    serializer_class = CareerPathSerializer
    # Career Development Paths: Auditor org-wide read; Manager/Employee
    # read-only scoped to team/own record; Contractor no access.
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadWrite | matrix_permission(aud='R', mgr='R*', emp='R*'),
    ]

    csv_filename = 'career-paths'
    csv_activity_label = 'career paths'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'current_role': 'Current role',
        'target_role': 'Target role',
        'department': 'Department',
        'milestones': 'Milestones',
        'target_date': 'Target date (YYYY-MM-DD)',
    }
    csv_required_fields = ['employee']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Current role', 'Target role', 'Department', 'Milestones', 'Target date']
    csv_sample_row = ['Taylor Morgan', 'Engineer', 'Senior Engineer', 'Engineering', 'Lead a cross-team project.', '2027-01-01']

    def csv_export_row(self, c):
        return [c.employee.name, c.current_role, c.target_role, c.department, c.milestones, c.target_date]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_hr_or_legacy(self.request) or _role_is(self.request, 'Department Head') or _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(self.request, qs, mgr='R*', emp='R*')


class SuccessionPlanViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """View-only for Department Head — succession planning isn't in their
    write list."""

    queryset = SuccessionPlan.objects.select_related('employee').all()
    serializer_class = SuccessionPlanSerializer
    # Succession Planning / 9-Box Grid: Auditor org-wide read; Manager
    # read-only scoped to their team; Employee/Contractor get none at all.
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadReadOnly | matrix_permission(aud='R', mgr='R*'),
    ]

    csv_filename = 'succession-plans'
    csv_activity_label = 'succession plans'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'potential_rating': 'Potential (Low, Medium, or High)',
        'performance_rating': 'Performance (Low, Medium, or High)',
        'successor_notes': 'Successor notes',
        'ready_now': 'Ready now (True or False)',
    }
    csv_required_fields = ['employee']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Potential', 'Performance', 'Successor notes', 'Ready now']
    csv_sample_row = ['Taylor Morgan', 'High', 'High', '', 'True']

    def csv_export_row(self, s):
        return [s.employee.name, s.potential_rating, s.performance_rating, s.successor_notes, s.ready_now]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(self.request, qs, mgr='R*')

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class RecruiterFeedbackViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Recruiter creates feedback notes on a placed/hired employee; HR
    views them (read-only for HR even though IsHR is OR'd in — enforced by
    the explicit role check in perform_create, not by http_method_names,
    since HR still needs list/retrieve)."""

    http_method_names = ['get', 'post', 'head', 'options']
    queryset = RecruiterFeedback.objects.select_related('employee').all()
    serializer_class = RecruiterFeedbackSerializer
    # Recruiter Feedback: Auditor gets org-wide read on top of Recruiter's
    # write access and HR's existing read (HR's "R" in the matrix is
    # already enforced not by the permission class but by the
    # perform_create role check below, unchanged).
    permission_classes = [IsAuthenticated, IsRecruiter | IsHR | matrix_permission(aud='R')]

    csv_filename = 'recruiter-feedback'
    csv_activity_label = 'recruiter feedback notes'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'given_by': 'Given by',
        'message': 'Message',
    }
    csv_required_fields = ['employee', 'message']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Given by', 'Message', 'Date']
    csv_sample_row = ['Taylor Morgan', 'Alex Rivera', 'Ramped up fast and integrated well with the team.']

    def csv_export_row(self, f):
        return [f.employee.name, f.given_by, f.message, f.created_at]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        if not _role_is(self.request, 'Recruiter'):
            raise PermissionDenied('Only Recruiter accounts can log feedback.')
        serializer.save(owner_id=owner_scope_id(self.request))


class EmployeeScoreView(APIView):
    """Value-Addition / Performance Scoring, "powered by EVO-AI" per the
    spec — see talent/scoring.py. Computed live from the employee's own
    goals + appraisals, nothing stored."""

    # Value-Addition / Performance Scoring: Auditor org-wide read; Manager
    # reads their own team's score; Employee reads only their own.
    permission_classes = [
        IsAuthenticated,
        IsHR | IsDepartmentHeadReadOnly | matrix_permission(self_scope_field='id', aud='R', mgr='R*', emp='R*'),
    ]

    def get(self, request, employee_id):
        employee = get_object_or_404(Employee, id=employee_id, owner_id=owner_scope_id(request))
        if _role_is(request, 'Department Head') and employee.department != request.user.profile.department:
            raise PermissionDenied("That employee isn't in your department.")
        # This view fetches its object manually (not via get_object()), so
        # DRF never runs matrix_permission's has_object_permission — do the
        # equivalent "own record or own team" check by hand here.
        if not is_hr_or_legacy(request) and not _role_is(request, 'Department Head') and not _role_is(request, 'Auditor'):
            profile = getattr(request.user, 'profile', None)
            is_self = bool(profile and profile.employee_id == employee.id)
            if not is_self and not is_manager_of(request, employee.id):
                raise PermissionDenied("You can only view your own or your team's performance score.")
        score, notes = compute_value_score(employee)
        return Response({'employee': employee.id, 'score': score, 'notes': notes})


class TalentDashboardSummaryView(APIView):
    """EVO-Talent's overview numbers, computed live from the user's own
    rows — nothing here is stored/cached. Overview row: Auditor sees the
    org-wide numbers read-only; Manager/Employee see the same shape
    narrowed to what they'd actually see on each underlying sub-page (each
    collection below is scoped with that sub-module's own matrix codes,
    not a blanket "Overview" code — e.g. Employee has zero access to
    Succession Planning on its own page, so it stays zeroed out here too)."""

    permission_classes = [IsAuthenticated, IsHR | IsAuditorReadOnly | matrix_permission(mgr='R*', emp='R*')]

    def get(self, request):
        uid = owner_scope_id(request)
        broad = is_hr_or_legacy(request) or _role_is(request, 'Auditor')

        def scope(qs, **codes):
            return qs if broad else scoped_queryset(request, qs, **codes)

        goals = scope(Goal.objects.filter(owner_id=uid), mgr='RW*', emp='RW*', con='R*')
        appraisals = scope(Appraisal.objects.filter(owner_id=uid), mgr='A*', emp='R*', con='R*')
        courses = Course.objects.filter(owner_id=uid)  # catalog, not employee-scoped
        enrollments = scope(Enrollment.objects.filter(course__owner_id=uid), mgr='R', emp='RW*', con='RW*')
        succession_plans = scope(SuccessionPlan.objects.filter(owner_id=uid), mgr='R*')
        career_paths = scope(CareerPath.objects.filter(owner_id=uid), mgr='R*', emp='R*')
        competency_ratings = scope(CompetencyRating.objects.filter(owner_id=uid), mgr='R*', emp='R*')

        goals_in_progress = goals.filter(status='In Progress').count()
        goals_completed = goals.filter(status='Completed').count()
        overdue_goals = goals.exclude(status='Completed').filter(
            target_date__isnull=False, target_date__lt=timezone.now().date()
        ).count()
        completed_enrollments = enrollments.filter(status='Completed').count()
        completion_rate = round(completed_enrollments / enrollments.count() * 100) if enrollments.count() else 0
        ready_now = succession_plans.filter(ready_now=True).count()

        # 9-box grid — potential x performance counts, for the frontend to
        # render as an actual 3x3 grid rather than a flat list.
        nine_box = {}
        for potential, _ in SuccessionPlan.RATING_CHOICES:
            for performance, _ in SuccessionPlan.RATING_CHOICES:
                count = succession_plans.filter(potential_rating=potential, performance_rating=performance).count()
                nine_box[f'{potential}_{performance}'] = count

        return Response(
            {
                'overview_stats': [
                    {'label': 'Goals in progress', 'value': str(goals_in_progress), 'change': '', 'href': '/dashboard/goals'},
                    {'label': 'Goals completed', 'value': str(goals_completed), 'change': '', 'href': '/dashboard/goals'},
                    {'label': 'Appraisals on file', 'value': str(appraisals.count()), 'change': '', 'href': '/dashboard/appraisals'},
                    {'label': 'Active courses', 'value': str(courses.filter(is_active=True).count()), 'change': '', 'href': '/dashboard/learning'},
                ],
                'kpis': [
                    {'label': 'Course completion rate', 'value': f'{completion_rate}%', 'href': '/dashboard/learning'},
                    {'label': 'Ready-now successors', 'value': str(ready_now), 'href': '/dashboard/succession-planning'},
                    {'label': 'Career paths mapped', 'value': str(career_paths.count()), 'href': '/dashboard/career-paths'},
                    {'label': 'Competencies tracked', 'value': str(competency_ratings.count()), 'href': '/dashboard/competency-mapping'},
                ],
                'nine_box': nine_box,
                'flags': {
                    'overdue_goals': overdue_goals,
                },
            }
        )
