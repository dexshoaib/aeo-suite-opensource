"""URL configuration for the AEO Suite backend.

Route map (grows as features land): /admin/ Django admin,
/api/v1/health/ liveness + database probe, /api/v1/organizations/ and
/api/v1/workspaces/ tenant viewsets, /api/auth/ JSON auth endpoints
(signup, login, logout, session) with allauth's own spec at
/api/auth/openapi.yaml, /api/schema/ the OpenAPI schema for the API
under /api/v1/, and /api/docs/ browsable Swagger UI.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts.views import OrganizationViewSet, WorkspaceViewSet
from apps.core.views import HealthView

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organizations")
router.register("workspaces", WorkspaceViewSet, basename="workspaces")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/", include(router.urls)),
    path("api/auth/", include("allauth.headless.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
