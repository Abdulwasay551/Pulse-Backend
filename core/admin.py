from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ActivityLog, DemoRequest


@admin.register(DemoRequest)
class DemoRequestAdmin(ModelAdmin):
    list_display = ['full_name', 'business_name', 'email', 'contact_number', 'created_at']
    search_fields = ['full_name', 'business_name', 'email']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
    list_display = ['message', 'owner', 'tone', 'created_at']
    list_filter = ['tone']
    search_fields = ['message']
