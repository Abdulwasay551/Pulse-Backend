from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import PayrollRun


@admin.register(PayrollRun)
class PayrollRunAdmin(ModelAdmin):
    list_display = ['period', 'owner', 'contractors', 'amount', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['period']
