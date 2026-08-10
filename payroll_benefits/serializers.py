from rest_framework import serializers

from core.permissions import owner_scope_id

from people.serializers import EmployeeLiteSerializer

from .models import (
    BankAccount,
    BenefitClaim,
    BenefitEnrollment,
    BenefitPlan,
    ComplianceEvent,
    PayrollRun,
    TaxProfile,
)


def _validate_owned_employee(employee, user_id):
    if employee.owner_id != user_id:
        raise serializers.ValidationError("That employee doesn't belong to you.")
    return employee


class PayrollRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = [
            'id', 'period', 'contractors', 'amount', 'currency', 'status',
            'discrepancy_flagged', 'audit_notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TaxProfileSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)

    class Meta:
        model = TaxProfile
        fields = [
            'id', 'employee', 'employee_detail', 'country', 'tax_id', 'filing_status',
            'compliance_status', 'notes', 'last_reviewed', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))


class ComplianceEventSerializer(serializers.ModelSerializer):
    calendar_status = serializers.SerializerMethodField()
    linked_payroll_run_period = serializers.CharField(source='linked_payroll_run.period', read_only=True, default=None)

    class Meta:
        model = ComplianceEvent
        fields = [
            'id', 'country', 'title', 'category', 'due_date', 'amount', 'currency',
            'responsible_party', 'linked_payroll_run', 'linked_payroll_run_period',
            'completed', 'notes', 'calendar_status', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_linked_payroll_run(self, run):
        if run and run.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That payroll run doesn't belong to you.")
        return run

    def get_calendar_status(self, obj):
        if obj.completed:
            return 'Completed'
        from datetime import date, timedelta
        today = date.today()
        if obj.due_date < today:
            return 'Overdue'
        if obj.due_date <= today + timedelta(days=14):
            return 'Due soon'
        return 'Upcoming'


class BankAccountSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    account_number = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = BankAccount
        fields = [
            'id', 'employee', 'employee_detail', 'bank_name', 'bank_country', 'account_holder_name',
            'account_number', 'account_number_last4', 'routing_number', 'account_type',
            'is_primary', 'verified', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'account_number_last4', 'created_at', 'updated_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def create(self, validated_data):
        account_number = validated_data.pop('account_number')
        validated_data['account_number_last4'] = account_number[-4:]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        account_number = validated_data.pop('account_number', None)
        if account_number:
            validated_data['account_number_last4'] = account_number[-4:]
        return super().update(instance, validated_data)


class BenefitPlanSerializer(serializers.ModelSerializer):
    enrolled_count = serializers.SerializerMethodField()

    class Meta:
        model = BenefitPlan
        fields = [
            'id', 'name', 'plan_type', 'provider', 'employee_cost', 'employer_cost',
            'description', 'is_active', 'enrolled_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_enrolled_count(self, obj):
        return obj.enrollments.filter(status='Enrolled').count()


class BenefitEnrollmentSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    plan_detail = BenefitPlanSerializer(source='plan', read_only=True)

    class Meta:
        model = BenefitEnrollment
        fields = [
            'id', 'employee', 'employee_detail', 'plan', 'plan_detail', 'coverage_level',
            'status', 'enrolled_at', 'terminated_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def validate_plan(self, plan):
        if plan.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That benefit plan doesn't belong to you.")
        return plan


class BenefitClaimSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeLiteSerializer(source='employee', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True, default='')

    class Meta:
        model = BenefitClaim
        fields = [
            'id', 'employee', 'employee_detail', 'plan', 'plan_name', 'claim_type', 'amount',
            'description', 'status', 'submitted_at', 'resolved_at',
        ]
        read_only_fields = ['id', 'submitted_at']

    def validate_employee(self, employee):
        return _validate_owned_employee(employee, owner_scope_id(self.context['request']))

    def validate_plan(self, plan):
        if plan and plan.owner_id != owner_scope_id(self.context['request']):
            raise serializers.ValidationError("That benefit plan doesn't belong to you.")
        return plan
