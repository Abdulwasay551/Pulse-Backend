from rest_framework import serializers

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


def initials_for(name: str) -> str:
    parts = [p for p in name.split() if p]
    return ''.join(p[0] for p in parts[:2]).upper()


class EmployeeLiteSerializer(serializers.ModelSerializer):
    """A trimmed view of Employee for nesting inside other serializers
    (attendance, shifts, leave, surveys, recognition, promotions, documents)."""

    initials = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ['id', 'name', 'initials', 'job_title', 'department']

    def get_initials(self, obj):
        return initials_for(obj.name)


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = EmployeeDocument
        fields = ['id', 'employee', 'employee_detail', 'doc_type', 'title', 'file', 'uploaded_at']
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
            'monthly_salary', 'source_candidate', 'portal_token', 'documents', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'portal_token', 'created_at', 'updated_at']

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


class EmployeePortalSerializer(serializers.ModelSerializer):
    """What an employee sees on their own public profile page (looked up by
    portal_token, no auth) — deliberately excludes email/phone and anything
    else internal beyond their own role/department/manager/tenure."""

    initials = serializers.SerializerMethodField()
    manager_name = serializers.CharField(source='manager.name', read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ['name', 'initials', 'job_title', 'department', 'manager_name', 'hire_date', 'status']

    def get_initials(self, obj):
        return initials_for(obj.name)


def _validate_owned_employee(employee, user_id):
    if employee.owner_id != user_id:
        raise serializers.ValidationError("That employee doesn't belong to you.")
    return employee


class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'employee', 'employee_detail', 'date', 'clock_in', 'clock_out',
            'overtime_hours', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)


class ShiftSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = Shift
        fields = ['id', 'employee', 'employee_detail', 'date', 'start_time', 'end_time', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            'id', 'employee', 'employee_detail', 'leave_type', 'start_date', 'end_date',
            'status', 'reason', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)


class SurveyResponseSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = SurveyResponse
        fields = ['id', 'survey', 'employee', 'employee_detail', 'rating', 'response_text', 'submitted_at']
        read_only_fields = ['id', 'submitted_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)

    def validate_survey(self, survey):
        if survey.owner_id != self.context['request'].user.id:
            raise serializers.ValidationError("That survey doesn't belong to you.")
        return survey


class SurveySerializer(serializers.ModelSerializer):
    responses = SurveyResponseSerializer(many=True, read_only=True)
    response_count = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = [
            'id', 'kind', 'title', 'question', 'is_open', 'responses',
            'response_count', 'average_rating', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_response_count(self, obj):
        return obj.responses.count()

    def get_average_rating(self, obj):
        ratings = [r.rating for r in obj.responses.all() if r.rating is not None]
        return round(sum(ratings) / len(ratings), 1) if ratings else None


class RecognitionSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = Recognition
        fields = ['id', 'employee', 'employee_detail', 'given_by', 'message', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)


class PromotionRequestSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = PromotionRequest
        fields = [
            'id', 'employee', 'employee_detail', 'from_title', 'to_title', 'from_department',
            'to_department', 'effective_date', 'status', 'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, self.context['request'].user.id)
