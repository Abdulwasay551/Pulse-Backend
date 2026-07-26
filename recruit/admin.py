from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline

from .models import (
    BackgroundCheck,
    Candidate,
    Client,
    Offboarding,
    OffboardingTask,
    OfferLetter,
    Onboarding,
    OnboardingTask,
    Requisition,
)


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
    list_display = ['name', 'role', 'client', 'owner', 'stage', 'source', 'ai_score', 'applied_at']
    list_filter = ['stage', 'source']
    search_fields = ['name', 'role', 'email']


@admin.register(OfferLetter)
class OfferLetterAdmin(ModelAdmin):
    list_display = ['candidate', 'job_title', 'status', 'sent_at', 'signed_at']
    list_filter = ['status']
    search_fields = ['candidate__name', 'job_title']


@admin.register(BackgroundCheck)
class BackgroundCheckAdmin(ModelAdmin):
    list_display = ['candidate', 'check_type', 'status', 'initiated_at', 'completed_at']
    list_filter = ['check_type', 'status']
    search_fields = ['candidate__name']


class OnboardingTaskInline(StackedInline):
    model = OnboardingTask
    extra = 0


@admin.register(Onboarding)
class OnboardingAdmin(ModelAdmin):
    list_display = ['candidate', 'start_date', 'status']
    list_filter = ['status']
    search_fields = ['candidate__name']
    inlines = [OnboardingTaskInline]


class OffboardingTaskInline(StackedInline):
    model = OffboardingTask
    extra = 0


@admin.register(Offboarding)
class OffboardingAdmin(ModelAdmin):
    list_display = ['candidate', 'last_working_day', 'status', 'rehire_eligible']
    list_filter = ['status', 'rehire_eligible']
    search_fields = ['candidate__name']
    inlines = [OffboardingTaskInline]
