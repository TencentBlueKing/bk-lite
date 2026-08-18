from django.urls import path

from apps.core.openapi import views

urlpatterns = [
    path("_me", views.me_view, name="openapi_me"),
    path("_auth", views.forward_auth_view, name="openapi_forward_auth"),
    path("_provider/traefik", views.provider_view, name="openapi_provider_traefik"),
    path("<str:service>/<path:sub_path>", views.invoke_view, name="openapi_invoke"),
]
