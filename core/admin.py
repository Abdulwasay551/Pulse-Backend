from django.contrib import admin
from django.contrib.auth import get_user_model
from unfold.admin import ModelAdmin, StackedInline
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import ActivityLog, DemoRequest, EmployeeInvite, Organization, UserProfile
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm


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
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    # Forms loaded from `unfold.forms`
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    inlines = [UserProfileInline]


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass

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
