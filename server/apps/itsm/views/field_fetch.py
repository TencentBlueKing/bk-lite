"""字段取数只接受字段键，执行配置从授权表单的发布快照读取。"""

from functools import wraps

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.openapi.registry import default_registry
from apps.core.openapi.schema import serializer_to_schema
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models import DataDictionary, DataTable
from apps.itsm.models.integration import Integration
from apps.itsm.services.form.capabilities import FIELD_CAPABILITIES
from apps.itsm.services.form.fetch import fetch_field, field_safe, freeze_schema, task_fetch_context, walk
from apps.itsm.services.form.validator import FormValidator, visible_field_keys
from apps.itsm.services.integrations import request_identity
from apps.itsm.services.service_access import visible_services
from apps.itsm.services.ticket.service import _find_node, _normalize_perm, workflow_schema
from apps.itsm.views.access import api_errors, domain_of, get_ticket
from apps.itsm.views.integrations import payload, require


def field_validation_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ValueError as exc:
            message = exc.args[0] if exc.args and isinstance(exc.args[0], str) else "请检查字段取数配置"
            return WebUtils.response_error(message)

    return wrapped


def integration_definition(item):
    result = {"id": item.id, "name": item.name, "kind": item.kind}
    if item.kind == "api" and item.config.get("transport") == "external":
        result["transport"] = "external"
        result["request_schema"] = item.config.get("request_schema", {"properties": {}})
    elif item.kind == "api":
        service, _, path = item.config["path"].partition("/")
        endpoint = default_registry.find(service, path, item.config.get("method", "GET"))
        result["request_schema"] = serializer_to_schema(endpoint.serializer_class)
    return result


@require_http_methods(["GET"])
@api_errors
def field_catalog(request):
    require(request, "form-Edit")
    domain = domain_of(request)
    return WebUtils.response_success(
        {
            "capabilities": FIELD_CAPABILITIES,
            "gateways": [
                {
                    "path": endpoint.path,
                    "method": endpoint.method,
                    "name": endpoint.summary or endpoint.path,
                    "request_schema": serializer_to_schema(endpoint.serializer_class),
                }
                for endpoint in default_registry.endpoints()
                if field_safe(Integration(kind="api", config={"path": endpoint.path, "method": endpoint.method}))
            ],
            "integrations": [integration_definition(item) for item in Integration.objects.filter(domain=domain, is_enabled=True) if field_safe(item)],
            "tables": [
                {
                    "key": table.key,
                    "name": table.name,
                    "columns": [{"key": column.key, "type": column.field_type} for column in table.fields.all()],
                }
                for table in DataTable.objects.filter(domain=domain).prefetch_related("fields")
            ],
            "dictionaries": list(DataDictionary.objects.filter(domain=domain).values("key", "name")),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@api_errors
@field_validation_errors
def field_fetch(request):
    body = payload(request)
    values = body.get("values") or {}
    if not isinstance(values, dict):
        raise ValueError("字段值必须是对象")
    if body.get("inspect") and not body.get("preview"):
        raise PermissionError()
    original = {}
    if body.get("preview"):
        require(request, "form-Edit")
        schema = freeze_schema(body.get("schema") or {}, domain_of(request), sampling_field=body.get("field") if body.get("inspect") else None)
        perm, context = {}, "preview"
    elif body.get("service_id"):
        require(request, "ticket-Add")
        service = visible_services(request, service_id=body["service_id"]).select_related("workflow__current_version").get()
        version = service.workflow.current_version
        schema = workflow_schema(version)
        perm = _find_node(version.design, node_type="submit").get("field_perm")
        context = f"version:{version.id}"
    elif body.get("ticket_id"):
        require(request, "ticket-Operate")
        ticket = get_ticket(request, body["ticket_id"])
        from apps.itsm.views.tickets import editable_task

        task = editable_task(request, ticket, body.get("task_id"))
        schema = workflow_schema(ticket.workflow_version)
        perm = _find_node(ticket.workflow_version.design, node_id=task.node_id).get("field_perm")
        context, original = task_fetch_context(ticket, task), ticket.form_data or {}
    else:
        raise ValueError("请指定服务或工单")
    validator = FormValidator(schema, _normalize_perm(perm))
    writable = {f.key for f, mode in validator._fields() if mode not in {"hidden", "readonly"}}
    visible = {f.key for f, mode in validator._fields() if mode != "hidden"}
    values = {**original, **{k: v for k, v in values.items() if k in writable}}
    key = body.get("field")
    field = next((f for f in walk(schema.get("fields", [])) if f["key"] == key), None)
    if key not in writable or not field or key not in visible_field_keys(validator.schema, values):
        raise PermissionError()
    if set((field.get("fetch") or {}).get("dependencies", [])) - visible:
        raise PermissionError()
    result = fetch_field(
        schema,
        key,
        values,
        request_identity(request),
        context=context,
        inspect=bool(body.get("inspect")),
        query=str(body.get("query") or "")[:100],
        page=max(1, min(1000, int(body.get("page") or 1))),
    )
    return WebUtils.response_success(result)


@csrf_exempt
@require_http_methods(["POST"])
@api_errors
@field_validation_errors
def field_gateway(request):
    """显式选择时引用网关，不通过读取目录创建集成。执行仍由网关鉴权。"""
    from apps.itsm.services.integrations import validate_config

    require(request, "form-Edit")
    config = validate_config("api", payload(request))
    if config.get("transport") == "external" or not field_safe(Integration(kind="api", config=config)):
        raise ValueError("字段只能选择平台查询接口")
    service, _, path = config["path"].partition("/")
    endpoint = default_registry.find(service, path, config["method"])
    item = Integration.objects.filter(domain=domain_of(request), kind="api", config=config, is_enabled=True).first()
    if item is None:
        item = Integration.objects.create(
            domain=domain_of(request),
            kind="api",
            config=config,
            is_enabled=True,
            name=(endpoint.summary or endpoint.path)[:128],
            created_by=request.user.username,
            updated_by=request.user.username,
        )
    return WebUtils.response_success(integration_definition(item))
