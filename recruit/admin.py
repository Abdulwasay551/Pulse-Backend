from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Candidate, Client, Requisition


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
