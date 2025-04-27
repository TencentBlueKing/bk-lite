from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
]

if settings.DEBUG:
    """
    开发时添加SWAGGER API DOC
    访问地址: http://127.0.0.1:8000/docs/
    """
    from drf_yasg import openapi
    from drf_yasg.views import get_schema_view
    from rest_framework import permissions

    schema_view = get_schema_view(
        openapi.Info(
            title="API文档",
            default_version="v1",
            description="API接口文档",
            terms_of_service="https://www.example.com/policies/terms/",
            contact=openapi.Contact(email="contact@example.com"),
            license=openapi.License(name="AGPL License"),
        ),
        public=True,
        permission_classes=[permissions.AllowAny],
    )
    urlpatterns += [
        path(
            "swagger/",
            schema_view.with_ui("swagger", cache_timeout=0),
            name="schema-swagger-ui",
        ),  # noqa
        path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),  # noqa
    ]

for app_config in apps.get_app_configs():
    app_name = app_config.name
    try:
        # app_name是apps.开头的，就import这个app的urls.py
        if app_name.startswith("apps."):
            urls_module = __import__(f"{app_name}.urls", fromlist=["urlpatterns"])
            url_path = app_name.split("apps.")[-1]
            urlpatterns.append(path(f"{url_path}/", include(urls_module)))

    except ImportError as e:  # noqa
        pass
