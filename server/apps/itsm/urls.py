from django.urls import path

from apps.itsm.views.health import health

urlpatterns = [
    path("api/health/", health, name="itsm-health"),
]
