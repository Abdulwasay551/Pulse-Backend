from datetime import date, timedelta

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.csv_io import CsvImportExportMixin, resolve_employee, resolve_related
from core.permissions import (
    IsDepartmentHeadCreateOnly,
    IsITManager,
    IsOwner,
    _role_is,
    owner_scope_id,
)

from .models import Asset, AssetIncident, BYODCompliance, SupportTicket
from .serializers import (
    AssetIncidentSerializer,
    AssetSerializer,
    BYODComplianceSerializer,
    SupportTicketSerializer,
)


def _resolve_asset(owner_id, raw_value):
    return resolve_related(Asset, owner_id, raw_value, match_fields=['asset_tag', 'name'], label='Asset')


class OwnedItAssetsViewSet(viewsets.ModelViewSet):
    """Shared base — every model in this app has its own `owner` field. IT
    Manager gets the same full-tier access as HR/Admin across this whole
    app."""

    permission_classes = [IsAuthenticated, IsOwner | IsITManager]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class AssetViewSet(CsvImportExportMixin, OwnedItAssetsViewSet):
    queryset = Asset.objects.select_related('assigned_to').all()
    serializer_class = AssetSerializer

    csv_filename = 'assets'
    csv_activity_label = 'assets'
    csv_import_fields = {
        'asset_tag': 'Asset tag',
        'name': 'Name',
        'category': 'Category (Laptop, Monitor, Phone, Tablet, Peripheral, or Other)',
        'serial_number': 'Serial number',
        'purchase_date': 'Purchase date (YYYY-MM-DD)',
        'warranty_expiry': 'Warranty expiry (YYYY-MM-DD)',
        'status': 'Status (In Stock, Assigned, In Repair, or Retired)',
        'assigned_to': 'Assigned to (employee name or email, optional)',
        'is_byod': 'BYOD (True or False)',
        'notes': 'Notes',
    }
    csv_required_fields = ['asset_tag', 'name']
    csv_field_parsers = {'assigned_to': resolve_employee}
    csv_export_header = [
        'Asset tag', 'Name', 'Category', 'Serial number', 'Purchase date', 'Warranty expiry',
        'Status', 'Assigned to', 'BYOD',
    ]
    csv_sample_row = ['LT-1042', 'MacBook Pro 14"', 'Laptop', 'C02XYZ123', '2026-01-10', '2029-01-10', 'In Stock', '', 'False', '']

    def csv_export_row(self, a):
        return [
            a.asset_tag, a.name, a.category, a.serial_number, a.purchase_date, a.warranty_expiry,
            a.status, a.assigned_to.name if a.assigned_to else '', a.is_byod,
        ]

    def perform_update(self, serializer):
        was_assigned = serializer.instance.assigned_to_id
        instance = serializer.save()
        uid = owner_scope_id(self.request)
        if not was_assigned and instance.assigned_to_id:
            log_activity(uid, f'{instance.name} ({instance.asset_tag}) assigned to {instance.assigned_to.name}', 'primary')
        elif was_assigned and not instance.assigned_to_id:
            log_activity(uid, f'{instance.name} ({instance.asset_tag}) unassigned', 'neutral')


class SupportTicketViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Department Head may create/list/retrieve a support ticket ("request
    IT help") for their own department's employees — never update/resolve
    it themselves; that absence of an update right is the approval gate
    (only HR/IT Manager act on what a Department Head creates)."""

    queryset = SupportTicket.objects.select_related('employee', 'asset').all()
    serializer_class = SupportTicketSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsITManager | IsDepartmentHeadCreateOnly]

    csv_filename = 'support-tickets'
    csv_activity_label = 'support tickets'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'asset': 'Asset (tag or name, optional)',
        'subject': 'Subject',
        'description': 'Description',
        'category': 'Category (Repair Request, Device Query, Access Request, or Other)',
        'priority': 'Priority (Low, Medium, or High)',
        'status': 'Status (Open, In Progress, Resolved, or Closed)',
    }
    csv_required_fields = ['employee', 'subject']
    csv_field_parsers = {'employee': resolve_employee, 'asset': _resolve_asset}
    csv_export_header = ['Employee', 'Asset', 'Subject', 'Category', 'Priority', 'Status']
    csv_sample_row = ['Taylor Morgan', 'LT-1042', 'Laptop running slow', 'Fans running loud, battery drains fast.', 'Device Query', 'Medium', 'Open']

    def csv_export_row(self, t):
        return [t.employee.name, t.asset.asset_tag if t.asset else '', t.subject, t.category, t.priority, t.status]

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
        instance = serializer.save()
        if previous_status not in ('Resolved', 'Closed') and instance.status in ('Resolved', 'Closed') and not instance.resolved_at:
            instance.resolved_at = timezone.now()
            instance.save(update_fields=['resolved_at'])


class AssetIncidentViewSet(CsvImportExportMixin, viewsets.ModelViewSet):
    """Same create-only Department Head pattern as SupportTicketViewSet."""

    queryset = AssetIncident.objects.select_related('employee', 'asset').all()
    serializer_class = AssetIncidentSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsITManager | IsDepartmentHeadCreateOnly]

    csv_filename = 'device-incidents'
    csv_activity_label = 'device incidents'
    csv_import_fields = {
        'asset': 'Asset (tag or name)',
        'employee': 'Employee (name or email, optional)',
        'incident_type': 'Type (Damage, Repair, Loss, Malfunction, or Other)',
        'description': 'Description',
        'incident_date': 'Incident date (YYYY-MM-DD)',
        'resolved': 'Resolved (True or False)',
        'resolution_notes': 'Resolution notes',
        'cost': 'Cost',
    }
    csv_required_fields = ['asset', 'incident_type']
    csv_field_parsers = {'asset': _resolve_asset, 'employee': resolve_employee}
    csv_export_header = ['Asset', 'Employee', 'Type', 'Incident date', 'Resolved', 'Cost']
    csv_sample_row = ['LT-1042', 'Taylor Morgan', 'Damage', 'Cracked screen corner.', '2026-07-15', 'False', '', '150']

    def csv_export_row(self, i):
        return [i.asset.asset_tag, i.employee.name if i.employee else '', i.incident_type, i.incident_date, i.resolved, i.cost]

    def get_queryset(self):
        qs = self.queryset.filter(owner_id=owner_scope_id(self.request))
        if _role_is(self.request, 'Department Head'):
            qs = qs.filter(employee__department=self.request.user.profile.department)
        return qs

    def perform_create(self, serializer):
        if _role_is(self.request, 'Department Head'):
            employee = serializer.validated_data.get('employee')
            if not employee or employee.department != self.request.user.profile.department:
                raise PermissionDenied("You can only file an incident for an employee in your department.")
        serializer.save(owner_id=owner_scope_id(self.request))


class BYODComplianceViewSet(CsvImportExportMixin, OwnedItAssetsViewSet):
    queryset = BYODCompliance.objects.select_related('employee', 'asset').all()
    serializer_class = BYODComplianceSerializer

    csv_filename = 'byod-compliance'
    csv_activity_label = 'BYOD compliance checks'
    csv_import_fields = {
        'employee': 'Employee (name or email)',
        'asset': 'Asset (tag or name)',
        'encryption_enabled': 'Encryption enabled (True or False)',
        'antivirus_installed': 'Antivirus installed (True or False)',
        'passcode_enabled': 'Passcode enabled (True or False)',
        'compliance_status': 'Compliance status (Compliant, Non-Compliant, or Pending Review)',
        'last_checked': 'Last checked (YYYY-MM-DD)',
        'notes': 'Notes',
    }
    csv_required_fields = ['employee', 'asset']
    csv_field_parsers = {'employee': resolve_employee, 'asset': _resolve_asset}
    csv_export_header = [
        'Employee', 'Asset', 'Encryption', 'Antivirus', 'Passcode', 'Compliance status', 'Last checked',
    ]
    csv_sample_row = ['Taylor Morgan', 'LT-1042', 'True', 'True', 'True', 'Compliant', '2026-07-01', '']

    def csv_export_row(self, b):
        return [
            b.employee.name, b.asset.asset_tag, b.encryption_enabled, b.antivirus_installed,
            b.passcode_enabled, b.compliance_status, b.last_checked,
        ]


class ItAssetsDashboardSummaryView(APIView):
    """EVO-IT & Asset Management's overview numbers, computed live from the
    user's own rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated, IsOwner | IsITManager]

    def get(self, request):
        uid = owner_scope_id(request)
        assets = Asset.objects.filter(owner_id=uid)
        tickets = SupportTicket.objects.filter(owner_id=uid)
        incidents = AssetIncident.objects.filter(owner_id=uid)
        byod_checks = BYODCompliance.objects.filter(owner_id=uid)

        today = date.today()
        assigned_count = assets.filter(status='Assigned').count()
        in_repair_count = assets.filter(status='In Repair').count()
        expiring_soon = assets.filter(
            warranty_expiry__isnull=False, warranty_expiry__gte=today, warranty_expiry__lte=today + timedelta(days=60)
        ).count()
        expired = assets.filter(warranty_expiry__isnull=False, warranty_expiry__lt=today).count()
        open_tickets = tickets.exclude(status__in=['Resolved', 'Closed']).count()
        unresolved_incidents = incidents.filter(resolved=False).count()
        non_compliant_byod = byod_checks.filter(compliance_status='Non-Compliant').count()

        return Response(
            {
                'overview_stats': [
                    {'label': 'Total assets', 'value': str(assets.count()), 'change': '', 'href': '/dashboard/asset-inventory'},
                    {'label': 'Assigned devices', 'value': str(assigned_count), 'change': '', 'href': '/dashboard/asset-inventory'},
                    {'label': 'Open support tickets', 'value': str(open_tickets), 'change': '', 'href': '/dashboard/it-support'},
                    {'label': 'In repair', 'value': str(in_repair_count), 'change': '', 'href': '/dashboard/device-tracker'},
                ],
                'kpis': [
                    {'label': 'Warranties expiring soon', 'value': str(expiring_soon), 'href': '/dashboard/warranty-tracking'},
                    {'label': 'Warranties expired', 'value': str(expired), 'href': '/dashboard/warranty-tracking'},
                    {'label': 'Unresolved incidents', 'value': str(unresolved_incidents), 'href': '/dashboard/device-tracker'},
                    {'label': 'BYOD devices non-compliant', 'value': str(non_compliant_byod), 'href': '/dashboard/byod-policy'},
                ],
            }
        )
