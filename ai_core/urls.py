from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AIFeatureOverrideView,
    AIFeatureSettingsView,
    AIProviderCatalogView,
    AIProviderCredentialViewSet,
    AIStatusView,
)

router = DefaultRouter()
router.register('credentials', AIProviderCredentialViewSet, basename='ai-credential')

urlpatterns = [
    path('providers/', AIProviderCatalogView.as_view(), name='ai-providers'),
    path('feature-settings/', AIFeatureSettingsView.as_view(), name='ai-feature-settings'),
    path('feature-settings/<str:feature_key>/', AIFeatureOverrideView.as_view(), name='ai-feature-override'),
    path('status/', AIStatusView.as_view(), name='ai-status'),
    path('', include(router.urls)),
]
