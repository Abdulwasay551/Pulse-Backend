from rest_framework import serializers

from core.permissions import owner_scope_id
from people.serializers import EmployeeLiteSerializer

from .models import (
    Appraisal,
    CareerPath,
    CompetencyRating,
    Course,
    Enrollment,
    Goal,
    RecruiterFeedback,
    SuccessionPlan,
)


def _validate_owned_employee(employee, user_id):
    if employee.owner_id != user_id:
        raise serializers.ValidationError("That employee doesn't belong to you.")
    return employee


class GoalSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = Goal
        fields = [
            'id', 'employee', 'employee_detail', 'title', 'description', 'target_date',
            'status', 'progress', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))


class AppraisalSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = Appraisal
        fields = [
            'id', 'employee', 'employee_detail', 'period', 'reviewer', 'overall_rating',
            'strengths', 'areas_for_improvement', 'status', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))


class CompetencyRatingSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = CompetencyRating
        fields = ['id', 'employee', 'employee_detail', 'competency', 'level', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))


class CourseSerializer(serializers.ModelSerializer):
    enrolled_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'duration_hours', 'is_active', 'enrolled_count', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_enrolled_count(self, obj):
        return obj.enrollments.count()


class EnrollmentSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id', 'course', 'course_title', 'employee', 'employee_detail', 'status',
            'completed_at', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def validate_course(self, course):
        if course.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That course doesn't belong to you.")
        return course


class CareerPathSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = CareerPath
        fields = [
            'id', 'employee', 'employee_detail', 'current_role', 'target_role', 'department',
            'milestones', 'target_date', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))


class RecruiterFeedbackSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = RecruiterFeedback
        fields = ['id', 'employee', 'employee_detail', 'given_by', 'message', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))


class SuccessionPlanSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = SuccessionPlan
        fields = [
            'id', 'employee', 'employee_detail', 'potential_rating', 'performance_rating',
            'successor_notes', 'ready_now', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))
