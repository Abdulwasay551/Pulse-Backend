from datetime import date, timedelta

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.activity import log_activity
from core.permissions import IsOwner

from .models import Asset, AssetIncident, BYODCompliance, SupportTicket
from .serializers import (
    AssetIncidentSerializer,
    AssetSerializer,
    BYODComplianceSerializer,
    SupportTicketSerializer,
)


class OwnedItAssetsViewSet(viewsets.ModelViewSet):
    """Shared base — every model in this app has its own `owner` field."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return self.queryset.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class AssetViewSet(OwnedItAssetsViewSet):
    queryset = Asset.objects.select_related('assigned_to').all()
    serializer_class = AssetSerializer

    def perform_update(self, serializer):
        was_assigned = serializer.instance.assigned_to_id
        instance = serializer.save()
        if not was_assigned and instance.assigned_to_id:
            log_activity(self.request.user, f'{instance.name} ({instance.asset_tag}) assigned to {instance.assigned_to.name}', 'primary')
        elif was_assigned and not instance.assigned_to_id:
            log_activity(self.request.user, f'{instance.name} ({instance.asset_tag}) unassigned', 'neutral')


class SupportTicketViewSet(OwnedItAssetsViewSet):
    queryset = SupportTicket.objects.select_related('employee', 'asset').all()
    serializer_class = SupportTicketSerializer

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        instance = serializer.save()
        if previous_status not in ('Resolved', 'Closed') and instance.status in ('Resolved', 'Closed') and not instance.resolved_at:
            instance.resolved_at = timezone.now()
            instance.save(update_fields=['resolved_at'])


class AssetIncidentViewSet(OwnedItAssetsViewSet):
    queryset = AssetIncident.objects.select_related('employee', 'asset').all()
    serializer_class = AssetIncidentSerializer


class BYODComplianceViewSet(OwnedItAssetsViewSet):
    queryset = BYODCompliance.objects.select_related('employee', 'asset').all()
    serializer_class = BYODComplianceSerializer


class ItAssetsDashboardSummaryView(APIView):
    """EVO-IT & Asset Management's overview numbers, computed live from the
    user's own rows — nothing here is stored/cached."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        user = request.user
        assets = Asset.objects.filter(owner=user)
        tickets = SupportTicket.objects.filter(owner=user)
        incidents = AssetIncident.objects.filter(owner=user)
        byod_checks = BYODCompliance.objects.filter(owner=user)

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
