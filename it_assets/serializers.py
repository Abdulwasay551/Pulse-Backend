from datetime import date, timedelta

from rest_framework import serializers

from people.serializers import EmployeeLiteSerializer

from .models import Asset, AssetIncident, BYODCompliance, SupportTicket


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
            'warranty_expiry', 'status', 'assigned_to', 'assigned_to_detail', 'assigned_at',
            'is_byod', 'notes', 'warranty_status', 'open_ticket_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_assigned_to(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)

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


class SupportTicketSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True, default='')

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'asset', 'asset_tag', 'employee', 'employee_detail', 'subject', 'description',
            'category', 'priority', 'status', 'created_at', 'resolved_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)

    def validate_asset(self, asset):
        if asset and asset.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That asset doesn't belong to you.")
        return asset


class AssetIncidentSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True)
    asset_name = serializers.CharField(source='asset.name', read_only=True)

    class Meta:
        model = AssetIncident
        fields = [
            'id', 'asset', 'asset_tag', 'asset_name', 'employee', 'employee_detail', 'incident_type',
            'description', 'incident_date', 'resolved', 'resolution_notes', 'cost', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)

    def validate_asset(self, asset):
        if asset.owner_id != self.context['request'].user.id:
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
        return _validate_owned_employee(employee, self.context['request'].user.id)

    def validate_asset(self, asset):
        if asset.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That asset doesn't belong to you.")
        return asset
