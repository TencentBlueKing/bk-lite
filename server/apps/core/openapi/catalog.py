"""两个接口目录入口共用的只读目录构造。"""

from apps.core.logger import openapi_logger as logger
from apps.core.openapi.registry import default_registry
from apps.core.openapi.schema import serializer_to_schema, success_response_schema


def build_docs_catalog():
    from apps.core.openapi.renderer import get_external_catalog

    internal = {}
    for endpoint in default_registry.endpoints():
        try:
            request_schema = serializer_to_schema(endpoint.serializer_class)
            response_schema = None
            if endpoint.response_serializer_class is not None:
                response_schema = success_response_schema(endpoint.response_serializer_class)
        except ValueError as exc:
            logger.warning(
                "event=openapi_catalog_endpoint_skipped method=%s path=%s failed_stage=schema_projection error_type=%s",
                endpoint.method,
                endpoint.path,
                type(exc).__name__,
            )
            continue

        internal.setdefault(endpoint.service, []).append(
            {
                "path": endpoint.path,
                "method": endpoint.method,
                "summary": endpoint.summary,
                "inject": endpoint.inject,
                "permission": endpoint.permission,
                "request_schema": request_schema,
                "response_schema": response_schema,
            }
        )

    services = [
        {
            "name": name,
            "kind": "internal",
            "endpoints": sorted(endpoints, key=lambda item: (item["path"], item["method"])),
        }
        for name, endpoints in sorted(internal.items())
    ]
    services.extend({"name": item["name"], "kind": "external", "doc_url": item["doc_url"]} for item in get_external_catalog())
    return {"services": services}
