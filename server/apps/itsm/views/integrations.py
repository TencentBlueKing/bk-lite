import json

from django.db.models import Case, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.mixinx import EncryptMixin
from apps.core.openapi.catalog import build_docs_catalog
from apps.core.utils.web_utils import WebUtils
from apps.itsm.models.integration import Integration
from apps.itsm.services.integrations import execute, request_identity, validate_config
from apps.itsm.views.access import api_errors, domain_of, has_permission, list_page


def require(request, permission):
    if not has_permission(request, permission):
        raise PermissionError()


def serialize(item, summary=False):
    result = {"id": item.id, "name": item.name, "kind": item.kind, "is_enabled": item.is_enabled, "updated_by": item.updated_by}
    if not summary:
        result["config"] = {**item.config}
        if item.kind == "todo" or item.config.get("transport") == "external":
            result["config"]["token"] = ""
            result["has_token"] = bool(item.config.get("token"))
    return result


def payload(request):
    data = json.loads(request.body or b"{}")
    if not isinstance(data, dict):
        raise ValueError("参数须为对象")
    return data


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_errors
def integrations(request):
    if request.method == "GET":
        summary = request.GET.get("summary") == "1"
        if not has_permission(request, "data-View") and not (summary and has_permission(request, "workflow-View")):
            raise PermissionError()
        items = Integration.objects.filter(domain=domain_of(request)).order_by("-id")
        return WebUtils.response_success(
            {
                "items": [serialize(item, summary) for item in items],
                "can_edit": has_permission(request, "data-Edit"),
                "can_add": has_permission(request, "data-Add"),
                "can_delete": has_permission(request, "data-Delete"),
            }
        )
    require(request, "data-Add")
    data = payload(request)
    name = str(data.get("name") or "").strip()
    if not name or len(name) > 128:
        raise ValueError("名称不能为空且不超过128字")
    config = validate_config(data.get("kind"), data.get("config"))
    if (data["kind"] == "todo" or config.get("transport") == "external") and config.get("token"):
        config["token"] = EncryptMixin.get_cipher_suite().encrypt(config["token"].encode()).decode()
    item = Integration.objects.create(
        name=name,
        kind=data["kind"],
        config=config,
        domain=domain_of(request),
        created_by=request.user.username,
        updated_by=request.user.username,
    )
    return WebUtils.response_success(serialize(item))


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@api_errors
def integration_detail(request, item_id):
    require(request, {"GET": "data-View", "PUT": "data-Edit", "DELETE": "data-Delete"}[request.method])
    item = get_object_or_404(Integration, pk=item_id, domain=domain_of(request))
    if request.method == "DELETE":
        # 保留发布流程的引用，使用停用代替物理删除。
        item.is_enabled = False
        item.save(update_fields=["is_enabled", "updated_at"])
        return WebUtils.response_success()
    if request.method == "PUT":
        data = payload(request)
        name = str(data.get("name", item.name)).strip()
        if not name or len(name) > 128 or ("is_enabled" in data and not isinstance(data["is_enabled"], bool)):
            raise ValueError("名称或启用状态无效")
        item.name = name
        if "config" in data:
            config = validate_config(item.kind, data["config"])
            if item.kind == "todo" or config.get("transport") == "external":
                config["token"] = (
                    EncryptMixin.get_cipher_suite().encrypt(config["token"].encode()).decode()
                    if config.get("token")
                    else (item.config.get("token", "") if config.get("url") == item.config.get("url") else "")
                )
            item.config = config
        item.is_enabled = data.get("is_enabled", item.is_enabled)
        item.updated_by = request.user.username
        item.save()
    result = serialize(item)
    result.update(_history(request.GET, item.runs, "run", ("created_by", "duration_ms")))
    result.update(_history(request.GET, item.deliveries, "delivery", ("attempts", "task_id", "event_key")))
    return WebUtils.response_success(result)


def _history(params, manager, kind, fields):
    priority = Value(0)
    if kind == "delivery":
        priority = Case(When(status="unknown", then=Value(0)), When(status="failed", then=Value(1)), default=Value(2))
    records = manager.annotate(priority=priority).order_by("priority", "-pk").values("id", "status", "code", "created_at", "priority", *fields)
    if status := params.get(f"{kind}_status"):
        records = records.filter(status=status)
    page = list_page(params, records, prefix=f"{kind}_")
    if cursor := params.get(f"{kind}_after"):
        rank, pk = map(int, cursor.split(":"))
        if rank not in (0, 1, 2) or not 0 < pk < 2**63:
            raise ValueError("无效的历史记录游标")
        rows = list(records.filter(Q(priority__gt=rank) | Q(priority=rank, pk__lt=pk))[:page.paginator.per_page])
    else:
        rows = list(page)
    after = f"{rows[-1]['priority']}:{rows[-1]['id']}" if rows else ""
    for row in rows:
        del row["priority"]
    return {
        "runs" if kind == "run" else "deliveries": rows,
        f"{kind}_count": page.paginator.count,
        f"{kind}_page": page.number,
        f"{kind}_next_cursor": after,
    }


@csrf_exempt
@require_http_methods(["POST"])
@api_errors
def integration_test(request, item_id):
    require(request, "data-Edit")
    item = get_object_or_404(Integration, pk=item_id, domain=domain_of(request))
    return WebUtils.response_success(execute(item, payload(request).get("inputs", {}), request_identity(request)))


@require_http_methods(["GET"])
@api_errors
def integration_catalog(request):
    require(request, "data-View")
    return WebUtils.response_success(build_docs_catalog())


@csrf_exempt
@require_http_methods(["POST"])
@api_errors
def retry_delivery(request, item_id, delivery_id):
    from apps.itsm.services.todo_sync import deliver

    require(request, "data-Edit")
    item = get_object_or_404(Integration, pk=item_id, domain=domain_of(request), kind="todo", is_enabled=True)
    row = get_object_or_404(item.deliveries, pk=delivery_id)
    if row.status != "failed":
        raise ValueError("只能重试失败的投递")
    deliver(row.id)
    row.refresh_from_db()
    return WebUtils.response_success({"status": row.status, "code": row.code})


@csrf_exempt
@require_http_methods(["POST"])
@api_errors
def reconcile_delivery(request, item_id, delivery_id):
    require(request, "data-Edit")
    item = get_object_or_404(Integration, pk=item_id, domain=domain_of(request), kind="todo", is_enabled=True)
    data = payload(request)
    if type(data.get("received")) is not bool or type(data.get("attempts")) is not int:
        raise ValueError("请确认接收方是否已收到该次投递")
    status = "done" if data["received"] else "pending"
    changed = item.deliveries.filter(pk=delivery_id, status="unknown", attempts=data["attempts"]).update(
        status=status, code="", updated_by=request.user.username, updated_by_domain=domain_of(request), updated_at=timezone.now()
    )
    if not changed:
        raise ValueError("投递状态已变更，请刷新后核对")
    return WebUtils.response_success({"status": status})
