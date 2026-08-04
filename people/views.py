from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.csv_io import csv_response, parse_csv_upload, row_to_record, suggest_mapping
from core.permissions import (
    IsDepartmentHeadCreateOnly,
    IsFinanceAdminReadOnly,
    IsDepartmentHeadReadOnly,
    IsHR,
    IsOwner,
    _role_is,
    owner_scope_id,
)

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

EMPLOYEE_IMPORT_FIELDS = {
    'name': 'Name',
    'email': 'Email',
    'phone': 'Phone',
    'job_title': 'Job title',
    'department': 'Department',
    'hire_date': 'Hire date',
    'status': 'Status',
}
EMPLOYEE_REQUIRED_FIELDS = ['name']


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('manager').prefetch_related('documents').all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        employee = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'{employee.name} added to the employee database', 'neutral')

    @action(detail=False, methods=['get'])
    def export(self, request):
        employees = self.get_queryset().order_by('name')
        header = ['Name', 'Email', 'Phone', 'Job title', 'Department', 'Hire date', 'Status']
        rows = [
            [e.name, e.email, e.phone, e.job_title, e.department, e.hire_date, e.status]
            for e in employees
        ]
        return csv_response('employees.csv', header, rows)

    @action(detail=False, methods=['post'], url_path='import/preview', parser_classes=[MultiPartParser, FormParser])
    def import_preview(self, request):
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
                'suggested_mapping': suggest_mapping(columns, EMPLOYEE_IMPORT_FIELDS),
                'fields': EMPLOYEE_IMPORT_FIELDS,
            }
        )

    @action(detail=False, methods=['post'], url_path='import/commit', parser_classes=[JSONParser])
    def import_commit(self, request):
        columns = request.data.get('columns')
        rows = request.data.get('rows')
        mapping = request.data.get('mapping')
        if not isinstance(columns, list) or not isinstance(rows, list) or not isinstance(mapping, dict):
            return Response(
                {'detail': 'Expected {columns, rows, mapping} from the preview step.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mapping = {k: v for k, v in mapping.items() if v in EMPLOYEE_IMPORT_FIELDS}
        mapped_fields = set(mapping.values())
        missing_required = [f for f in EMPLOYEE_REQUIRED_FIELDS if f not in mapped_fields]
        if missing_required:
            return Response(
                {'detail': f'Map a column to the required field(s): {", ".join(missing_required)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = 0
        errors = []
        for i, row in enumerate(rows, start=2):
            record = row_to_record(columns, row, mapping)
            record = {k: v for k, v in record.items() if v != ''}
            missing = [f for f in EMPLOYEE_REQUIRED_FIELDS if not record.get(f)]
            if missing:
                errors.append(f'Row {i}: {", ".join(missing)} is required')
                continue

            serializer = EmployeeSerializer(data=record, context={'request': request})
            if not serializer.is_valid():
                first_field, first_errors = next(iter(serializer.errors.items()))
                errors.append(f'Row {i}: {first_field} — {first_errors[0]}')
                continue

            serializer.save(owner_id=owner_scope_id(request))
            created += 1

        if created:
            log_activity(owner_scope_id(request), f'Imported {created} employee{"s" if created != 1 else ""} from CSV', 'neutral')

        return Response({'created': created, 'errors': errors})


class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    """No IsOwner here — EmployeeDocument has no `owner` field of its own
    (only its parent Employee does), same reasoning as Recruit's
    OnboardingTask/OffboardingTask. Ownership comes from scoping the
    queryset to the parent's owner."""

    queryset = EmployeeDocument.objects.select_related('employee').all()
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsAuthenticated, IsHR]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return self.queryset.filter(employee__owner_id=owner_scope_id(self.request))


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


class AttendanceRecordViewSet(viewsets.ModelViewSet):
    """Finance Admin gets a narrow read-only slice (to inform payroll/
    overtime calculations); Department Head gets read-only scoped to their
    own department; HR/Admin keep full CRUD."""

    queryset = AttendanceRecord.objects.select_related('employee').all()
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsFinanceAdminReadOnly | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class ShiftViewSet(viewsets.ModelViewSet):
    """Department Head gets read-only access scoped to their own department
    on top of HR/Admin's full CRUD."""

    queryset = Shift.objects.select_related('employee').all()
    serializer_class = ShiftSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class LeaveRequestViewSet(viewsets.ModelViewSet):
    """Department Head may create/list/retrieve a leave request for their
    own department's employees — never update/delete; that absence of an
    update right is the approval gate (only HR/Admin decide Approved/
    Rejected)."""

    queryset = LeaveRequest.objects.select_related('employee').all()
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadCreateOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
        serializer.save(owner_id=owner_scope_id(self.request))

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        leave = serializer.save()
        if leave.status != previous_status and leave.status in ('Approved', 'Rejected'):
            tone = 'primary' if leave.status == 'Approved' else 'maroon'
            log_activity(owner_scope_id(self.request), f'{leave.employee.name}’s {leave.leave_type} leave {leave.status.lower()}', tone)


class SurveyViewSet(viewsets.ModelViewSet):
    queryset = Survey.objects.prefetch_related('responses__employee').all()
    serializer_class = SurveySerializer
    permission_classes = [IsAuthenticated, IsOwner]

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
    permission_classes = [IsAuthenticated, IsHR | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(survey__owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs


class RecognitionViewSet(viewsets.ModelViewSet):
    queryset = Recognition.objects.select_related('employee').all()
    serializer_class = RecognitionSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadReadOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        recognition = serializer.save(owner_id=owner_scope_id(self.request))
        log_activity(owner_scope_id(self.request), f'{recognition.employee.name} recognized: {recognition.message[:60]}', 'primary')


class PromotionRequestViewSet(viewsets.ModelViewSet):
    """Department Head may create/list/retrieve a promotion request for
    their own department's employees — never update/delete; approval
    (setting status='Approved', which actually mutates the Employee row
    below) stays HR/Admin-only."""

    queryset = PromotionRequest.objects.select_related('employee').all()
    serializer_class = PromotionRequestSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsDepartmentHeadCreateOnly]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data['employee']
            if employee.department != self.request.user.profile.department:
                raise PermissionDenied("That employee isn't in your department.")
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

    permission_classes = [IsAuthenticated, IsHR]

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
            }
        )
