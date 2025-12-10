import logging
import traceback  # noqa

from django.apps import apps
from django.conf import settings  # noqa
from django.contrib import admin
from django.urls import include, path

logger = logging.getLogger(__name__)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
]

for app_config in apps.get_app_configs():
    app_name = app_config.name
    try:
        # app_name是apps.开头的，就import这个app的urls.py
        if app_name.startswith("apps."):
            urls_module = __import__(f"{app_name}.urls", fromlist=["urlpatterns"])
            url_path = app_name.split("apps.")[-1]
            urlpatterns.append(path(f"api/v1/{url_path}/", include(urls_module)))

    except Exception as e:
        # 其他异常需要记录详细错误信息
        logger.error(f"Failed to load URLs for app '{app_name}': {e}")
        logger.error(traceback.format_exc())
        print(f"[ERROR] Failed to load URLs for app '{app_name}': {e}")
        print(traceback.format_exc())
