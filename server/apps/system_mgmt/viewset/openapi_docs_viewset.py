from rest_framework import permissions
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.openapi.registry import default_registry
from apps.core.utils.web_utils import WebUtils


def _field_spec(field):
    from rest_framework.fields import empty

    spec = {
        "type": type(field).__name__.removesuffix("Field").lower() or "field",
        "required": bool(field.required),
    }
    if field.default is not empty and not callable(field.default):
        spec["default"] = field.default
    choices = getattr(field, "choices", None)
    if choices:
        spec["choices"] = list(choices)
    for attr in ("min_value", "max_value"):
        value = getattr(field, attr, None)
        if value is not None:
            spec[attr] = value
    return spec


def build_docs_catalog():
    from apps.core.openapi.renderer import get_external_catalog

    internal = {}
    for endpoint in default_registry.endpoints():
        internal.setdefault(endpoint.service, []).append(
            {
                "path": endpoint.path,
                "method": endpoint.method,
                "summary": endpoint.summary,
                "inject": endpoint.inject,
                "permission": endpoint.permission,
                "request_schema": {
                    name: _field_spec(field)
                    for name, field in endpoint.serializer_class().fields.items()
                },
            }
        )

    external = [
        {"name": item["name"], "kind": "external", "doc_url": item["doc_url"]}
        for item in get_external_catalog()
    ]

    services = [
        {
            "name": name,
            "kind": "internal",
            "endpoints": sorted(endpoints, key=lambda item: (item["path"], item["method"])),
        }
        for name, endpoints in sorted(internal.items())
    ] + external
    return {"services": services}


class OpenAPIDocsViewSet(ViewSet):
    """系统管理只读接口文档：投影内部注册表与外部 doc_url，权限走 openapi_docs-View。"""

    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @HasPermission("openapi_docs-View")
    def list(self, request):
        return WebUtils.response_success(build_docs_catalog())
