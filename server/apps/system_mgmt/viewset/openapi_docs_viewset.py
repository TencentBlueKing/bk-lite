from rest_framework import permissions
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.openapi.catalog import build_docs_catalog
from apps.core.utils.web_utils import WebUtils


class OpenAPIDocsViewSet(ViewSet):
    """系统管理只读接口文档：投影内部注册表与外部 doc_url，权限走 openapi_docs-View。"""

    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @HasPermission("openapi_docs-View")
    def list(self, request):
        return WebUtils.response_success(build_docs_catalog())
