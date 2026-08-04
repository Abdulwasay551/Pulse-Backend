from datetime import date, timedelta

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
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


class OwnedItAssetsViewSet(viewsets.ModelViewSet):
    """Shared base — every model in this app has its own `owner` field. IT
    Manager gets the same full-tier access as HR/Admin across this whole
    app."""

    permission_classes = [IsAuthenticated, IsOwner | IsITManager]

    def get_queryset(self):
        return self.queryset.filter(owner_id=owner_scope_id(self.request))

    def perform_create(self, serializer):
        serializer.save(owner_id=owner_scope_id(self.request))


class AssetViewSet(OwnedItAssetsViewSet):
    queryset = Asset.objects.select_related('assigned_to').all()
    serializer_class = AssetSerializer

    def perform_update(self, serializer):
        was_assigned = serializer.instance.assigned_to_id
        instance = serializer.save()
        uid = owner_scope_id(self.request)
        if not was_assigned and instance.assigned_to_id:
            log_activity(uid, f'{instance.name} ({instance.asset_tag}) assigned to {instance.assigned_to.name}', 'primary')
        elif was_assigned and not instance.assigned_to_id:
            log_activity(uid, f'{instance.name} ({instance.asset_tag}) unassigned', 'neutral')


class SupportTicketViewSet(viewsets.ModelViewSet):
    """Department Head may create/list/retrieve a support ticket ("request
    IT help") for their own department's employees — never update/resolve
    it themselves; that absence of an update right is the approval gate
    (only HR/IT Manager act on what a Department Head creates)."""

    queryset = SupportTicket.objects.select_related('employee', 'asset').all()
    serializer_class = SupportTicketSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsITManager | IsDepartmentHeadCreateOnly]

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


class AssetIncidentViewSet(viewsets.ModelViewSet):
    """Same create-only Department Head pattern as SupportTicketViewSet."""

    queryset = AssetIncident.objects.select_related('employee', 'asset').all()
    serializer_class = AssetIncidentSerializer
    permission_classes = [IsAuthenticated, IsOwner | IsITManager | IsDepartmentHeadCreateOnly]

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


class BYODComplianceViewSet(OwnedItAssetsViewSet):
    queryset = BYODCompliance.objects.select_related('employee', 'asset').all()
    serializer_class = BYODComplianceSerializer


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
