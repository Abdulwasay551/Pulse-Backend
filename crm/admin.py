from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ActivityLog, Candidate, Client, PayrollRun, Requisition


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ['name', 'owner', 'industry', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['name', 'industry', 'contact_name', 'contact_email']


@admin.register(Requisition)
class RequisitionAdmin(ModelAdmin):
    list_display = ['title', 'client', 'owner', 'status', 'priority', 'posted_at']
    list_filter = ['status', 'priority']
    search_fields = ['title', 'client__name']


@admin.register(Candidate)
class CandidateAdmin(ModelAdmin):
    list_display = ['name', 'role', 'client', 'owner', 'stage', 'source', 'applied_at']
    list_filter = ['stage', 'source']
    search_fields = ['name', 'role']


@admin.register(PayrollRun)
class PayrollRunAdmin(ModelAdmin):
    list_display = ['period', 'owner', 'contractors', 'amount', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['period']


@admin.register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
    list_display = ['message', 'owner', 'tone', 'created_at']
    list_filter = ['tone']
    search_fields = ['message']
