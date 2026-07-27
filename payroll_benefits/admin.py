from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    BankAccount,
    BenefitClaim,
    BenefitEnrollment,
    BenefitPlan,
    ComplianceEvent,
    PayrollRun,
    TaxProfile,
)


@admin.register(PayrollRun)
class PayrollRunAdmin(ModelAdmin):
    list_display = ['period', 'owner', 'contractors', 'amount', 'currency', 'status', 'discrepancy_flagged', 'created_at']
    list_filter = ['status', 'currency', 'discrepancy_flagged']
    search_fields = ['period']


@admin.register(TaxProfile)
class TaxProfileAdmin(ModelAdmin):
    list_display = ['employee', 'country', 'filing_status', 'compliance_status', 'owner']
    list_filter = ['country', 'compliance_status']
    search_fields = ['employee__name', 'country', 'tax_id']


@admin.register(ComplianceEvent)
class ComplianceEventAdmin(ModelAdmin):
    list_display = ['title', 'country', 'category', 'due_date', 'completed', 'owner']
    list_filter = ['category', 'completed', 'country']
    search_fields = ['title', 'country']


@admin.register(BankAccount)
class BankAccountAdmin(ModelAdmin):
    list_display = ['employee', 'bank_name', 'account_number_last4', 'account_type', 'is_primary', 'verified', 'owner']
    list_filter = ['account_type', 'is_primary', 'verified']
    search_fields = ['employee__name', 'bank_name']


@admin.register(BenefitPlan)
class BenefitPlanAdmin(ModelAdmin):
    list_display = ['name', 'plan_type', 'provider', 'employee_cost', 'employer_cost', 'is_active', 'owner']
    list_filter = ['plan_type', 'is_active']
    search_fields = ['name', 'provider']


@admin.register(BenefitEnrollment)
class BenefitEnrollmentAdmin(ModelAdmin):
    list_display = ['employee', 'plan', 'coverage_level', 'status', 'enrolled_at', 'owner']
    list_filter = ['status', 'coverage_level']
    search_fields = ['employee__name', 'plan__name']


@admin.register(BenefitClaim)
class BenefitClaimAdmin(ModelAdmin):
    list_display = ['employee', 'claim_type', 'amount', 'status', 'submitted_at', 'owner']
    list_filter = ['status']
    search_fields = ['employee__name', 'claim_type']
