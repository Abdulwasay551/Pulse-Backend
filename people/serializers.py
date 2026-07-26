from rest_framework import serializers

from .models import Employee, EmployeeDocument


def initials_for(name: str) -> str:
    parts = [p for p in name.split() if p]
    return ''.join(p[0] for p in parts[:2]).upper()


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeDocument
        fields = ['id', 'employee', 'doc_type', 'title', 'file', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

    def validate_employee(self, employee):
        if employee.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That employee doesn't belong to you.")
        return employee


class EmployeeSerializer(serializers.ModelSerializer):
    initials = serializers.SerializerMethodField()
    manager_name = serializers.CharField(source='manager.name', read_only=True, default=None)
    direct_reports_count = serializers.SerializerMethodField()
    documents = EmployeeDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'name', 'initials', 'email', 'phone', 'job_title', 'department',
            'manager', 'manager_name', 'direct_reports_count', 'hire_date', 'status',
            'source_candidate', 'documents', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_initials(self, obj):
        return initials_for(obj.name)

    def get_direct_reports_count(self, obj):
        return obj.direct_reports.count()

    def validate_manager(self, manager):
        if manager is not None:
            if manager.owner_id != self.context['request'].user.id:
                raise serializers.ValidationError("That manager doesn't belong to you.")
            if self.instance is not None and manager.id == self.instance.id:
                raise serializers.ValidationError("An employee can't manage themselves.")
        return manager

    def validate_source_candidate(self, candidate):
        if candidate is not None and candidate.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That candidate doesn't belong to you.")
        return candidate
