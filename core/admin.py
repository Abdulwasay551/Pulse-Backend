from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import DemoRequest


@admin.register(DemoRequest)
class DemoRequestAdmin(ModelAdmin):
    list_display = ['full_name', 'business_name', 'email', 'contact_number', 'created_at']
    search_fields = ['full_name', 'business_name', 'email']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
