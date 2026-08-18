from django.urls import path

from apps.core.openapi import views

urlpatterns = [
    path("_me", views.me_view, name="openapi_me"),
    path("<str:service>/<path:sub_path>", views.invoke_view, name="openapi_invoke"),
]
