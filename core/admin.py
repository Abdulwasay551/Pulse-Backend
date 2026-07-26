from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ActivityLog, DemoRequest, EmployeeInvite, Organization, UserProfile


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name']


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    list_display = ['user', 'role', 'organization', 'employee']
    list_filter = ['role']
    search_fields = ['user__username', 'user__email']


@admin.register(EmployeeInvite)
class EmployeeInviteAdmin(ModelAdmin):
    list_display = ['employee', 'email', 'organization', 'accepted_at', 'created_at']
    search_fields = ['email']


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
