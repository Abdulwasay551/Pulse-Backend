from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline

from .models import Employee, EmployeeDocument


class EmployeeDocumentInline(StackedInline):
    model = EmployeeDocument
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(ModelAdmin):
    list_display = ['name', 'job_title', 'department', 'manager', 'status', 'owner']
    list_filter = ['status', 'department']
    search_fields = ['name', 'email', 'job_title']
    inlines = [EmployeeDocumentInline]
