import logging

from django.apps import apps
from django.contrib import admin
from django.urls import include, path

logger = logging.getLogger(__name__)

API_VERSION = "v1"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    # OpenAPI 统一网关（specs/changes/openapi-unified-gateway）：
    # 顶层静态挂载以获得干净的 /openapi/v1/ 前缀，不走下方 api/v1/<app>/ 动态循环
    path("openapi/v1/", include("apps.core.openapi.urls")),
]

for app_config in apps.get_app_configs():
    app_name = app_config.name
    if not app_name.startswith("apps."):
        continue

    try:
        urls_module = __import__(f"{app_name}.urls", fromlist=["urlpatterns"])
        url_path = app_name.removeprefix("apps.")
        urlpatterns.append(path(f"api/{API_VERSION}/{url_path}/", include(urls_module)))
    except ModuleNotFoundError:
        # App 没有 urls.py 是正常情况，静默跳过
        logger.debug(f"App '{app_name}' has no urls module, skipping")
    except Exception as e:
        # urls.py 存在但有语法/导入错误，中断启动
        print(e)
        logger.exception(e)
        logger.exception(f"Failed to load URLs for app '{app_name}'")
        raise
