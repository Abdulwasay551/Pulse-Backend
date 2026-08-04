from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .auth_views import (
    ChangePasswordView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegisterView,
    ResetPasswordView,
)
from .demo_views import DemoRequestCreateView
from .hr_views import EmployeeAccountCreateView, EmployeeInviteView, InviteDetailView
from .my_views import (
    ClockInView,
    ClockOutView,
    MyBenefitClaimsView,
    MyDashboardView,
    MyOnboardingChecklistView,
    MySupportTicketsView,
    MyTalentView,
)
from .views import AnnouncementViewSet

router = DefaultRouter()
router.register('announcements', AnnouncementViewSet, basename='announcement')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/refresh/', RefreshView.as_view(), name='auth-refresh'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
    path('auth/password/change/', ChangePasswordView.as_view(), name='auth-password-change'),
    path('auth/password/forgot/', ForgotPasswordView.as_view(), name='auth-password-forgot'),
    path('auth/password/reset/', ResetPasswordView.as_view(), name='auth-password-reset'),
    path('demo-requests/', DemoRequestCreateView.as_view(), name='demo-request-create'),
    # HR: employee account provisioning
    path('employee-invites/', EmployeeInviteView.as_view(), name='employee-invite'),
    path('invites/<uuid:token>/', InviteDetailView.as_view(), name='invite-detail'),
    path('employee-accounts/', EmployeeAccountCreateView.as_view(), name='employee-account-create'),
    # Employee-role self-service
    path('my/dashboard/', MyDashboardView.as_view(), name='my-dashboard'),
    path('my/clock-in/', ClockInView.as_view(), name='my-clock-in'),
    path('my/clock-out/', ClockOutView.as_view(), name='my-clock-out'),
    path('my/onboarding-checklist/', MyOnboardingChecklistView.as_view(), name='my-onboarding-checklist'),
    path('my/talent/', MyTalentView.as_view(), name='my-talent'),
    path('my/benefit-claims/', MyBenefitClaimsView.as_view(), name='my-benefit-claims'),
    path('my/support-tickets/', MySupportTicketsView.as_view(), name='my-support-tickets'),
    path('', include(router.urls)),
]
