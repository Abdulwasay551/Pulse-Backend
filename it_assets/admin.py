from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Asset, AssetIncident, BYODCompliance, SupportTicket


@admin.register(Asset)
class AssetAdmin(ModelAdmin):
    list_display = ['asset_tag', 'name', 'category', 'status', 'assigned_to', 'warranty_expiry', 'is_byod', 'owner']
    list_filter = ['category', 'status', 'is_byod']
    search_fields = ['asset_tag', 'name', 'serial_number']


@admin.register(SupportTicket)
class SupportTicketAdmin(ModelAdmin):
    list_display = ['subject', 'employee', 'asset', 'category', 'priority', 'status', 'created_at', 'owner']
    list_filter = ['category', 'priority', 'status']
    search_fields = ['subject', 'employee__name']


@admin.register(AssetIncident)
class AssetIncidentAdmin(ModelAdmin):
    list_display = ['asset', 'incident_type', 'incident_date', 'resolved', 'cost', 'owner']
    list_filter = ['incident_type', 'resolved']
    search_fields = ['asset__asset_tag', 'asset__name']


@admin.register(BYODCompliance)
class BYODComplianceAdmin(ModelAdmin):
    list_display = ['employee', 'asset', 'compliance_status', 'last_checked', 'owner']
    list_filter = ['compliance_status']
    search_fields = ['employee__name', 'asset__asset_tag']
