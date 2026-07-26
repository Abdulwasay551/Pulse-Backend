from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.csv_io import csv_response, parse_csv_upload, row_to_record, suggest_mapping
from core.permissions import IsOwner

from .models import Employee, EmployeeDocument
from .serializers import EmployeeDocumentSerializer, EmployeeSerializer

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
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        employee = serializer.save(owner=self.request.user)
        log_activity(self.request.user, f'{employee.name} added to the employee database', 'neutral')

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

            serializer.save(owner=request.user)
            created += 1

        if created:
            log_activity(request.user, f'Imported {created} employee{"s" if created != 1 else ""} from CSV', 'neutral')

        return Response({'created': created, 'errors': errors})


class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    """No IsOwner here — EmployeeDocument has no `owner` field of its own
    (only its parent Employee does), same reasoning as Recruit's
    OnboardingTask/OffboardingTask. Ownership comes from scoping the
    queryset to the parent's owner."""

    queryset = EmployeeDocument.objects.select_related('employee').all()
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return self.queryset.filter(employee__owner=self.request.user)


class PeopleDashboardSummaryView(APIView):
    """EVO-People's overview numbers, computed live from the user's own
    employee rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        employees = Employee.objects.filter(owner=request.user)
        total = employees.count()
        active = employees.filter(status='Active').count()
        on_leave = employees.filter(status='On Leave').count()

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

        return Response(
            {
                'overview_stats': [
                    {'label': 'Total employees', 'value': str(total), 'change': '', 'href': '/dashboard/employee-database'},
                    {'label': 'Active', 'value': str(active), 'change': '', 'href': '/dashboard/employee-database'},
                    {'label': 'On leave', 'value': str(on_leave), 'change': '', 'href': '/dashboard/employee-database'},
                    {'label': 'Departments', 'value': str(len(department_counts)), 'change': '', 'href': '/dashboard/org-chart'},
                ],
                'department_breakdown': department_breakdown,
                'status_breakdown': status_breakdown,
            }
        )
