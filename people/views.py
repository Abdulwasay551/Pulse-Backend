from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.access_matrix import matrix_permission, scoped_queryset
from core.activity import log_activity
from core.csv_io import CsvImportExportMixin, resolve_employee
from core.permissions import (
    IsAuditorReadOnly,
    IsDepartmentHeadCreateOnly,
    IsFinanceAdminReadOnly,
    IsDepartmentHeadReadOnly,
    IsHR,
    IsOwner,
    _role_is,
    is_hr_or_legacy,
    owner_scope_id,
)

# Roles the Control Hierarchy Matrix gives broad (non-self-scoped) read
# access to a resource — get_queryset methods below skip straight to
# "everything in the tenant" for these rather than routing through
# scoped_queryset, since that helper's job is narrowing to "own
# record"/"own team", not broadening.
_BROAD_READ_ROLES = ('IT Manager', 'Finance Admin', 'Auditor', 'Recruiter')


def _has_broad_read(request):
    return any(_role_is(request, r) for r in _BROAD_READ_ROLES)

from .certificates import render_recognition_certificate
from .models import (
    AttendanceRecord,
    Employee,
    EmployeeDocument,
    LeaveRequest,
    PromotionRequest,
    Recognition,
    Shift,
    Survey,
    SurveyResponse,
)
from .serializers import (
    AttendanceRecordSerializer,
    EmployeeDocumentSerializer,
    EmployeePortalSerializer,
    EmployeeSerializer,
    LeaveRequestSerializer,
    PromotionRequestSerializer,
    RecognitionSerializer,
    ShiftSerializer,
    SurveyResponseSerializer,
    SurveySerializer,
)


class EmployeeViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('manager').prefetch_related('documents').all()
    serializer_class = EmployeeSerializer
    # Employee Database (+ Organizational Chart, which reads off this same
    # data): IT Manager/Finance Admin/Auditor/Recruiter get org-wide read,
    # Manager sees their own team, Employee/Contractor see + edit their own
    # record (`self_scope_field='id'` since Employee *is* the employee row).
    permission_classes = [
        IsAuthenticated,
        IsOwner
        | IsDepartmentHeadReadOnly
        | matrix_permission(self_scope_field='id', ita='R', fa='R', aud='R', mgr='R*', rec='R', emp='RW*', con='RW*'),
    ]

    csv_filename = 'employees'
    csv_activity_label = 'employees'
    csv_import_fields = {
        'name': 'Name',
        'email': 'Email',
        'phone': 'Phone',
        'job_title': 'Role title',
        'department': 'Department',
        'client_name': 'Client name',
        'salary_type': 'Salary type (Hourly, Salaried, or Contract)',
        'location': 'Location',
        'hire_date': 'Hire date (YYYY-MM-DD)',
        'permanent_date': 'Permanent date (YYYY-MM-DD)',
        'status': 'Status (Active, On Leave, or Terminated)',
        'monthly_salary': 'Monthly salary',
    }
    csv_required_fields = ['name']
    csv_export_header = [
        'Name', 'Email', 'Phone', 'Role title', 'Department', 'Client name', 'Salary type',
        'Location', 'Hire date', 'Permanent date', 'Status', 'Monthly salary',
    ]
    csv_sample_row = [
        'Taylor Morgan', 'taylor.morgan@example.com', '+1 555-0100', 'Senior Engineer', 'Engineering',
        'Northbridge Talent', 'Salaried', 'Remote — Austin', '2026-01-15', '', 'Active', '8500',
    ]

    def get_csv_export_queryset(self):
        return self.get_queryset().order_by('name')

    def csv_export_row(self, e):
        return [
            e.name, e.email, e.phone, e.job_title, e.department, e.client_name, e.salary_type,
            e.location, e.hire_date, e.permanent_date, e.status, e.monthly_salary,
        ]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(department=self.request.user.profile.department)
        if _has_broad_read(self.request):
            return qs
        return scoped_queryset(self.request, qs, self_scope_field='id', mgr='R*', emp='RW*', con='RW*')

    def perform_create(self, serializer):
        employee = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'{employee.name} added to the employee database', 'neutral')


class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    """No IsOwner here — EmployeeDocument has no `owner` field of its own
    (only its parent Employee does), same reasoning as Recruit's
    OnboardingTask/OffboardingTask. Ownership comes from scoping the
    queryset to the parent's owner."""

    queryset = EmployeeDocument.objects.select_related('employee').all()
    serializer_class = EmployeeDocumentSerializer
    # "Employee Database (incl. ESS + Documents)" is one matrix row — same
    # codes as EmployeeViewSet above.
    permission_classes = [
        IsAuthenticated,
        IsHR | matrix_permission(owner_getter=lambda obj: obj.employee.owner_id, ita='R', fa='R', aud='R', mgr='R*', rec='R', emp='RW*', con='RW*'),
    ]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = self.queryset.filter(employee__owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request) or _has_broad_read(self.request):
            return qs
        return scoped_queryset(self.request, qs, mgr='R*', emp='RW*', con='RW*')


class EmployeePortalView(APIView):
    """The public, no-login profile page an employee sees at their own
    portal link (frontend: /employee-portal/[token]) — same reasoning as
    EVO-Recruit's CandidatePortalView."""

    permission_classes = [AllowAny]

    def get(self, request, token):
        employee = get_object_or_404(Employee, portal_token=token)
        return Response(EmployeePortalSerializer(employee).data)


class OwnedByEmployeeViewSet(viewsets.ModelViewSet):
    """Shared base for the Attendance Management resources with a plain
    owner-only access story (Shift) — each has its own `owner` field
    (unlike EmployeeDocument), so plain IsOwner + owner-filtered queryset
    works. AttendanceRecord/LeaveRequest have their own narrower-role
    wiring below and no longer use this base."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class AttendanceRecordViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Finance Admin gets a narrow read-only slice (to inform payroll/
    overtime calculations); Department Head gets read-only scoped to their
    own department; HR/Admin keep full CRUD."""

    queryset = AttendanceRecord.objects.select_related('employee').all()
    serializer_class = AttendanceRecordSerializer
    # This one viewset covers both the matrix's "Clock-in/Clock-out
    # Tracking" and "Overtime Tracking" rows (they're the same model here,
    # split only by a ?view= query param on the frontend) — codes below are
    # the union of both rows per role. Employee/Contractor's actual
    # clock-in/out already goes through the dedicated /my/clock-in|out/
    # endpoints (core/my_views.py), so R* here just covers viewing their
    # own history; Manager gets RW* to cover approving/adjusting their
    # team's overtime (row 2's RW*/A*), which slightly over-grants write on
    # raw clock times too — an accepted approximation given the shared
    # model.
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsFinanceAdminReadOnly | IsDepartmentHeadReadOnly | matrix_permission(aud='R', mgr='RW*', emp='R*', con='R*'),
    ]

    csv_filename = 'attendance-records'
    csv_activity_label = 'attendance records'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'date': 'Date (YYYY-MM-DD)',
        'clock_in': 'Clock in (HH:MM)',
        'clock_out': 'Clock out (HH:MM)',
        'overtime_hours': 'Overtime (hours)',
        'notes': 'Notes',
    }
    csv_required_fields = ['employee']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Date', 'Clock in', 'Clock out', 'Overtime (hours)', 'Notes']
    csv_sample_row = ['Taylor Morgan', '2026-08-01', '09:00', '17:30', '0', '']

    def csv_export_row(self, r):
        return [r.employee.name, r.date, r.clock_in, r.clock_out, r.overtime_hours, r.notes]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, mgr='RW*', emp='R*', con='R*')

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class ShiftViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own department
    on top of HR/Admin's full CRUD."""

    queryset = Shift.objects.select_related('employee').all()
    serializer_class = ShiftSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadReadOnly | matrix_permission(aud='R', mgr='RW*', emp='R*', con='R*'),
    ]

    csv_filename = 'shifts'
    csv_activity_label = 'shifts'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'date': 'Date (YYYY-MM-DD)',
        'start_time': 'Start time (HH:MM)',
        'end_time': 'End time (HH:MM)',
        'notes': 'Notes',
    }
    csv_required_fields = ['employee', 'start_time', 'end_time']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Date', 'Start time', 'End time', 'Notes']
    csv_sample_row = ['Taylor Morgan', '2026-08-01', '09:00', '17:00', '']

    def csv_export_row(self, s):
        return [s.employee.name, s.date, s.start_time, s.end_time, s.notes]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        return scoped_queryset(self.request, qs, mgr='RW*', emp='R*', con='R*')

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class LeaveRequestViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head may create/list/retrieve a leave request for their
    own department's employees — never update/delete; that absence of an
    update right is the approval gate (only HR/Admin decide Approved/
    Rejected)."""

    queryset = LeaveRequest.objects.select_related('employee').all()
    serializer_class = LeaveRequestSerializer
    # Employee/Contractor get real self-service here (create + view their
    # own time-off requests) — Manager's 'A*' covers approving their team's
    # (see _covers: Approve implies read+write, gated to own team by the
    # matrix engine's MGR handling).
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadCreateOnly | matrix_permission(aud='R', mgr='A*', emp='RW*', con='RW*'),
    ]

    csv_filename = 'time-off'
    csv_activity_label = 'time off requests'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'leave_type': 'Type (Vacation, Sick, Personal, Unpaid, or Other)',
        'start_date': 'Start date (YYYY-MM-DD)',
        'end_date': 'End date (YYYY-MM-DD)',
        'hours': 'Hours',
        'status': 'Status (Pending, Approved, or Rejected)',
        'reason': 'Reason',
    }
    csv_required_fields = ['employee', 'start_date', 'end_date']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Type', 'Start date', 'End date', 'Hours', 'Status', 'Reason']
    csv_sample_row = ['Taylor Morgan', 'Vacation', '2026-09-01', '2026-09-05', '40', 'Pending', 'Family trip']

    def csv_export_row(self, r):
        return [r.employee.name, r.leave_type, r.start_date, r.end_date, r.hours, r.status, r.reason]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Finance Admin'):
            return qs
        return scoped_queryset(self.request, qs, mgr='A*', emp='RW*', con='RW*')

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role in ('Employee', 'Contractor'):
            # Self-service: can only ever file a leave request for
            # themselves, whatever `employee` was submitted.
            if not profile.employee_id:
                raise PermissionDenied('Your account has no linked employee record.')
            serializer.validated_data['employee'] = profile.employee
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        leave = serializer.save()
        if leave.status != previous_status and leave.status in ('Approved', 'Rejected'):
            tone = 'primary' if leave.status == 'Approved' else 'maroon'
            log_activity(owner_scope_id(self.request), f'{leave.employee.name}’s {leave.leave_type} leave {leave.status.lower()}', tone)


def _parse_questions(owner_id, raw_value):
    """Splits a pipe-separated CSV cell into the `questions` list field —
    e.g. "How was your week? | Any blockers?" — since a JSON list has no
    single natural spreadsheet-cell representation."""
    questions = [q.strip() for q in raw_value.split('|') if q.strip()]
    if not questions:
        return None, 'at least one question is required'
    return questions, None


class SurveyViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    queryset = Survey.objects.prefetch_related('responses__employee').all()
    serializer_class = SurveySerializer
    # The matrix's "Surveys"/"Pulse Checks" rows are about *responding*
    # (SurveyResponseViewSet below carries the real EMP/CON grant) — this
    # read-only Auditor/Employee/Contractor access here is just so a
    # self-service "what can I answer" view has something to list; there's
    # no dedicated employee-facing survey-taking screen yet, only the API
    # support for one.
    permission_classes = [IsAuthenticated, IsOwner | matrix_permission(aud='R', mgr='R', emp='R', con='R')]

    csv_filename = 'surveys'
    csv_activity_label = 'surveys'
    csv_import_fields = {
        'kind': 'Kind (Survey or Pulse Check)',
        'title': 'Title',
        'questions': 'Questions (separate multiple with a pipe: |)',
        'frequency': 'Frequency (Yearly or Bi-yearly — Pulse Check only)',
        'is_open': 'Open (True or False)',
    }
    csv_required_fields = ['title', 'questions']
    csv_field_parsers = {'questions': _parse_questions}
    csv_export_header = ['Kind', 'Title', 'Questions', 'Frequency', 'Open', 'Responses']
    csv_sample_row = ['Pulse Check', 'How was your week?', 'How manageable was your workload? | Do you feel supported?', 'Bi-yearly', 'True']

    def csv_export_row(self, s):
        return [s.kind, s.title, ' | '.join(s.questions), s.frequency, s.is_open, s.responses.count()]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class SurveyResponseViewSet(viewsets.ModelViewSet):
    """No IsOwner — SurveyResponse has no `owner` field of its own, scoped
    via its parent Survey's owner, same reasoning as EmployeeDocument.
    Department Head gets read-only access scoped to their own department."""

    queryset = SurveyResponse.objects.select_related('employee', 'survey').all()
    serializer_class = SurveyResponseSerializer
    # Employee/Contractor get 'W*' — write (submit) their own response,
    # deliberately not read-back, matching the matrix's literal "Write
    # Only" for these two rows (Surveys/Pulse Checks) rather than 'RW*'.
    # Manager reads their team's responses ('R', not starred in the doc,
    # but MGR is always team-scoped regardless — see access_matrix).
    permission_classes = [
        IsAuthenticated,
        IsHR
        | IsDepartmentHeadReadOnly
        | matrix_permission(owner_getter=lambda obj: obj.survey.owner_id, aud='R', mgr='R', emp='W*', con='W*'),
    ]

    def get_queryset(self):
        qs = self.queryset.filter(survey__owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        return scoped_queryset(self.request, qs, mgr='R', emp='W*', con='W*')

    def perform_create(self, serializer):
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.role in ('Employee', 'Contractor'):
            if not profile.employee_id:
                raise PermissionDenied('Your account has no linked employee record.')
            serializer.validated_data['employee'] = profile.employee
        serializer.save()


class RecognitionViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    queryset = Recognition.objects.select_related('employee').all()
    serializer_class = RecognitionSerializer
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadReadOnly | matrix_permission(aud='R', mgr='RW', emp='RW*', con='R*'),
    ]

    csv_filename = 'recognitions'
    csv_activity_label = 'recognitions'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'recognition_type': (
            'Recognition type (Employee of the Month, Work Anniversary, Above & Beyond, '
            'Team Player, Innovation Award, or Milestone Achievement)'
        ),
        'given_by': 'Given by',
        'message': 'Message',
    }
    csv_required_fields = ['employee']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = ['Employee', 'Recognition type', 'Given by', 'Message', 'Date']
    csv_sample_row = ['Taylor Morgan', 'Above & Beyond', 'Jordan Ellis', 'Shipped the migration ahead of schedule.']

    def csv_export_row(self, r):
        return [r.employee.name, r.recognition_type, r.given_by, r.message, r.created_at]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        return scoped_queryset(self.request, qs, mgr='RW', emp='RW*', con='R*')

    def perform_create(self, serializer):
        recognition = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'{recognition.employee.name} recognized: {recognition.recognition_type}', 'primary')

    @action(detail=True, methods=['get'])
    def certificate(self, request, pk=None):
        recognition = self.get_object()
        pdf_bytes = render_recognition_certificate(recognition)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f'{recognition.employee.name.replace(" ", "-")}-recognition-certificate.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PromotionRequestViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head may create/list/retrieve a promotion request for
    their own department's employees — never update/delete; approval
    (setting status='Approved', which actually mutates the Employee row
    below) stays HR/Admin-only."""

    queryset = PromotionRequest.objects.select_related('employee').all()
    serializer_class = PromotionRequestSerializer
    # Manager initiates + first-approves for their own team ('W*/A*' in the
    # doc, both covered by matrix_permission treating 'A' as read+write);
    # Employee only ever reads their own; Contractor gets none at all.
    permission_classes = [
        IsAuthenticated,
        IsOwner | IsDepartmentHeadCreateOnly | matrix_permission(aud='R', mgr='A*', emp='R*'),
    ]

    csv_filename = 'promotion-requests'
    csv_activity_label = 'promotion requests'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'from_title': 'From title',
        'to_title': 'To title',
        'from_department': 'From department',
        'to_department': 'To department',
        'effective_date': 'Effective date (YYYY-MM-DD)',
        'status': 'Status (Pending, Approved, or Rejected)',
        'notes': 'Notes',
    }
    csv_required_fields = ['employee']
    csv_field_parsers = {'employee': resolve_employee}
    csv_export_header = [
        'Employee', 'From title', 'To title', 'From department', 'To department', 'Effective date', 'Status', 'Notes',
    ]
    csv_sample_row = ['Taylor Morgan', 'Engineer', 'Senior Engineer', 'Engineering', 'Engineering', '2026-10-01', 'Pending', '']

    def csv_export_row(self, p):
        return [
            p.employee.name, p.from_title, p.to_title, p.from_department, p.to_department,
            p.effective_date, p.status, p.notes,
        ]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if is_hr_or_legacy(self.request):
            return qs
        if _role_is(self.request, 'Department Head'):
            return qs.filter(employee__department=self.request.user.profile.department)
        if _role_is(self.request, 'Finance Admin') or _role_is(self.request, 'Auditor'):
            return qs
        return scoped_queryset(self.request, qs, mgr='A*', emp='R*')

    def perform_create(self, serializer):
        from core.access_matrix import is_manager_of

        employee = serializer.validated_data['employee']
        if _role_is(self.request, 'Department Head'):
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
        elif not is_hr_or_legacy(self.request) and not is_manager_of(self.request, employee.id):
            raise PermissionDenied("You can only request a promotion/transfer for someone on your team.")
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        promo = serializer.save()
        if promo.status != previous_status and promo.status == 'Approved':
            # Reflect the promotion/transfer straight onto the employee's
            # own record — the whole point of the workflow is that approving
            # it actually changes their title/department, not just logs it.
            changed = False
            if promo.to_title:
                promo.employee.job_title = promo.to_title
                changed = True
            if promo.to_department:
                promo.employee.department = promo.to_department
                changed = True
            if changed:
                promo.employee.save(update_fields=['job_title', 'department'])
            log_activity(owner_scope_id(self.request), f'{promo.employee.name} promoted/transferred to {promo.to_title or promo.to_department}', 'primary')


class PeopleDashboardSummaryView(APIView):
    """EVO-People's overview numbers, computed live from the user's own
    employee rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated, IsHR | IsAuditorReadOnly]

    def get(self, request):
        uid = owner_scope_id(request)
        employees = Employee.objects.filter(owner_id=uid)
        total = employees.count()
        active = employees.filter(status='Active').count()
        on_leave = employees.filter(status='On Leave').count()
        terminated = employees.filter(status='Terminated').count()

        department_counts = {}
        for dept in employees.exclude(department='').values_list('department', flat=True):
            department_counts[dept] = department_counts.get(dept, 0) + 1
        department_breakdown = [
            {'label': label, 'percent': round(count / total * 100) if total else 0}
            for label, count in sorted(department_counts.items(), key=lambda kv: -kv[1])
        ]

        status_breakdown = [
            {'label': label, 'count': employees.filter(status=value).count()}
            for value, label in Employee.STATUS_CHOICES
        ]

        # Attrition rate — a simple, honest headline KPI (terminated ÷ total
        # ever employed) rather than a fabricated historical trend, since
        # there's no month-by-month headcount snapshot stored anywhere.
        attrition_rate = round(terminated / total * 100) if total else 0

        pending_leave = LeaveRequest.objects.filter(owner_id=uid, status='Pending').count()
        pending_promotions = PromotionRequest.objects.filter(owner_id=uid, status='Pending').count()
        open_surveys = Survey.objects.filter(owner_id=uid, is_open=True).count()

        return Response(
            {
                'overview_stats': [
                    {'label': 'Total employees', 'value': str(total), 'change': '', 'href': '/dashboard/employee-database'},
                    {'label': 'Active', 'value': str(active), 'change': '', 'href': '/dashboard/employee-database'},
                    {'label': 'On leave', 'value': str(on_leave), 'change': '', 'href': '/dashboard/leave-requests'},
                    {'label': 'Departments', 'value': str(len(department_counts)), 'change': '', 'href': '/dashboard/org-chart'},
                ],
                'department_breakdown': department_breakdown,
                'status_breakdown': status_breakdown,
                'kpis': [
                    {'label': 'Attrition rate', 'value': f'{attrition_rate}%', 'href': '/dashboard/employee-database'},
                    {'label': 'Pending leave requests', 'value': str(pending_leave), 'href': '/dashboard/leave-requests'},
                    {'label': 'Pending promotions', 'value': str(pending_promotions), 'href': '/dashboard/promotions'},
                    {'label': 'Open surveys', 'value': str(open_surveys), 'href': '/dashboard/surveys'},
                ],
                'flags': {
                    'pending_leave': pending_leave,
                    'open_surveys': open_surveys,
                },
            }
        )
