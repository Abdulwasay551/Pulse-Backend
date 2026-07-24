from django.urls import path

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
]
