from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Appraisal, CareerPath, CompetencyRating, Course, Enrollment, Goal, SuccessionPlan


@admin.register(Goal)
class GoalAdmin(ModelAdmin):
    list_display = ['employee', 'title', 'status', 'progress', 'owner']
    list_filter = ['status']


@admin.register(Appraisal)
class AppraisalAdmin(ModelAdmin):
    list_display = ['employee', 'period', 'overall_rating', 'status', 'owner']
    list_filter = ['status']


@admin.register(CompetencyRating)
class CompetencyRatingAdmin(ModelAdmin):
    list_display = ['employee', 'competency', 'level', 'owner']


@admin.register(Course)
class CourseAdmin(ModelAdmin):
    list_display = ['title', 'duration_hours', 'is_active', 'owner']
    list_filter = ['is_active']


@admin.register(Enrollment)
class EnrollmentAdmin(ModelAdmin):
    list_display = ['employee', 'course', 'status', 'completed_at']
    list_filter = ['status']


@admin.register(CareerPath)
class CareerPathAdmin(ModelAdmin):
    list_display = ['employee', 'current_role', 'target_role', 'owner']


@admin.register(SuccessionPlan)
class SuccessionPlanAdmin(ModelAdmin):
    list_display = ['employee', 'potential_rating', 'performance_rating', 'ready_now', 'owner']
    list_filter = ['potential_rating', 'performance_rating', 'ready_now']
