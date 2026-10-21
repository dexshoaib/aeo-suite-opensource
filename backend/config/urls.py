"""URL configuration - chunk 0.2 skeleton.

Routes grow per task: /api/v1/health/ (Task 3), /api/auth/ allauth
headless (Task 7), /api/schema/ + /api/docs/ (Task 8), tenant viewsets
(Task 6).
"""

from django.contrib import admin
from django.urls import path

from apps.core.views import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthView.as_view(), name="health"),
]
