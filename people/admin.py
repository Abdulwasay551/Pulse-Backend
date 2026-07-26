from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline

from .models import (
    AttendanceRecord,
    Employee,
    EmployeeDocument,
    LeaveRequest,
    PromotionRequest,
    Recognition,
    Shift,
    Survey,
    SurveyResponse,
)


class EmployeeDocumentInline(StackedInline):
    model = EmployeeDocument
    extra = 0


@admin.register(Employee)
class EmployeeAdmin(ModelAdmin):
    list_display = ['name', 'job_title', 'department', 'manager', 'status', 'owner']
    list_filter = ['status', 'department']
    search_fields = ['name', 'email', 'job_title']
    inlines = [EmployeeDocumentInline]


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(ModelAdmin):
    list_display = ['employee', 'date', 'clock_in', 'clock_out', 'overtime_hours', 'owner']
    list_filter = ['date']


@admin.register(Shift)
class ShiftAdmin(ModelAdmin):
    list_display = ['employee', 'date', 'start_time', 'end_time', 'owner']
    list_filter = ['date']


@admin.register(LeaveRequest)
class LeaveRequestAdmin(ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'status', 'owner']
    list_filter = ['leave_type', 'status']


class SurveyResponseInline(StackedInline):
    model = SurveyResponse
    extra = 0


@admin.register(Survey)
class SurveyAdmin(ModelAdmin):
    list_display = ['title', 'kind', 'is_open', 'owner']
    list_filter = ['kind', 'is_open']
    inlines = [SurveyResponseInline]


@admin.register(Recognition)
class RecognitionAdmin(ModelAdmin):
    list_display = ['employee', 'given_by', 'created_at', 'owner']


@admin.register(PromotionRequest)
class PromotionRequestAdmin(ModelAdmin):
    list_display = ['employee', 'from_title', 'to_title', 'status', 'owner']
    list_filter = ['status']
