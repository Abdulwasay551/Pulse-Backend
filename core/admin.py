from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from unfold.admin import ModelAdmin, StackedInline

from .models import ActivityLog, DemoRequest, EmployeeInvite, Organization, UserProfile

User = get_user_model()


class UserProfileInline(StackedInline):
    """Lets a superuser (Admin) pick a role/organization/department for a
    new login on the same screen as creating the User itself — otherwise
    provisioning IT Manager/Finance Admin accounts is a two-page process
    (create the User, then separately create its UserProfile)."""

    model = UserProfile
    extra = 0
    fk_name = 'user'


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin, ModelAdmin):
    inlines = [UserProfileInline]


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name']


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    list_display = ['user', 'role', 'organization', 'department', 'employee']
    list_filter = ['role', 'department']
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
