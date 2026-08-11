from datetime import date, timedelta

from rest_framework import serializers

from core.permissions import owner_scope_id

from people.serializers import EmployeeLiteSerializer

from .models import Asset, AssetIncident, AssetRecovery, BYODCompliance, SupportTicket


def _validate_owned_employee(employee, user_id):
    if employee and employee.owner_id != user_id:
        raise serializers.ValidationError("That employee doesn't belong to you.")
    return employee


class AssetSerializer(serializers.ModelSerializer):
    assigned_to_detail = EmployeeLiteSerializer(source='assigned_to', read_only=True)
    warranty_status = serializers.SerializerMethodField()
    open_ticket_count = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            'id', 'asset_tag', 'name', 'category', 'serial_number', 'purchase_date',
            'warranty_expiry', 'warranty_provider', 'warranty_notes', 'warranty_document',
            'status', 'assigned_to', 'assigned_to_detail', 'assigned_at',
            'is_byod', 'notes', 'warranty_status', 'open_ticket_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_assigned_to(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def get_warranty_status(self, obj):
        if not obj.warranty_expiry:
            return 'Unknown'
        today = date.today()
        if obj.warranty_expiry < today:
            return 'Expired'
        if obj.warranty_expiry <= today + timedelta(days=60):
            return 'Expiring Soon'
        return 'Active'

    def get_open_ticket_count(self, obj):
        return obj.tickets.exclude(status__in=['Resolved', 'Closed']).count()


def _format_duration(delta):
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes < 60:
        return f'{max(total_minutes, 0)}m'
    hours, minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f'{hours}h {minutes}m' if minutes else f'{hours}h'
    days, hours = divmod(hours, 24)
    return f'{days}d {hours}h' if hours else f'{days}d'


class SupportTicketSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True, default='')
    resolution_time = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'asset', 'asset_tag', 'employee', 'employee_detail', 'subject', 'description',
            'category', 'priority', 'status', 'created_at', 'resolved_at', 'resolution_time',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def validate_asset(self, asset):
        if asset and asset.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That asset doesn't belong to you.")
        return asset

    def get_resolution_time(self, obj):
        if not obj.resolved_at:
            return None
        return _format_duration(obj.resolved_at - obj.created_at)


class AssetIncidentSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True)
    asset_name = serializers.CharField(source='asset.name', read_only=True)

    class Meta:
        model = AssetIncident
        fields = [
            'id', 'asset', 'asset_tag', 'asset_name', 'employee', 'employee_detail', 'incident_type',
            'description', 'incident_date', 'resolved', 'resolution_notes', 'cost', 'currency', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def validate_asset(self, asset):
        if asset.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That asset doesn't belong to you.")
        return asset


class AssetRecoverySerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True)
    asset_name = serializers.CharField(source='asset.name', read_only=True)

    class Meta:
        model = AssetRecovery
        fields = [
            'id', 'asset', 'asset_tag', 'asset_name', 'employee', 'employee_detail', 'last_working_day',
            'status', 'recovered_at', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'recovered_at', 'created_at', 'updated_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def validate_asset(self, asset):
        if asset.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That asset doesn't belong to you.")
        return asset


class BYODComplianceSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True)

    class Meta:
        model = BYODCompliance
        fields = [
            'id', 'asset', 'asset_tag', 'employee', 'employee_detail', 'encryption_enabled',
            'antivirus_installed', 'passcode_enabled', 'compliance_status', 'last_checked', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def validate_asset(self, asset):
        if asset.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That asset doesn't belong to you.")
        return asset
