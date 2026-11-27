"""流程设计器通过作业平台的资源权限查询可绑定的脚本和执行目标。"""

from collections import defaultdict

from django.apps import apps
from django.views.decorators.http import require_GET
from rest_framework.exceptions import PermissionDenied

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.core.utils.web_utils import WebUtils
from apps.itsm.services.form.schema import LAYOUT_ONLY
from apps.itsm.services.form.table_columns import TABLE_FIELDS, configured_table_columns
from apps.itsm.services.form.validator import LIST_TYPES
from apps.itsm.views.access import api_errors, domain_of


def scoped_resources(request, view_class):
    view = view_class()
    rows = view.queryset.filter(domain=domain_of(request))
    try:
        team = view._validate_current_team_permission(request)
    except PermissionDenied as exc:
        raise PermissionError("无权访问当前组织") from exc
    rows = rows.filter(build_json_membership_query(rows, "team", [team]))
    return view.get_queryset_by_permission(request, rows).order_by("name", "pk")


def public_params(params):
    return [
        {
            "name": p.get("name") or p["key"],
            "label": p.get("label") or p.get("name") or p["key"],
            "description": p.get("description") or "",
            "type": p.get("type") or "text",
            "options": (p.get("options") or []) if p.get("type") == "enum" else [],
            "is_required": bool(p.get("is_required")),
        }
        for p in params
    ]


def supports_params(params):
    return isinstance(params, list) and all(isinstance(p, dict) and (p.get("name") or p.get("key")) and not p.get("is_encrypted") for p in params)


@require_GET
@api_errors
@HasPermission("workflow-Edit,workflow-Draft")
@HasPermission("script_library-View", app_name="job")
@HasPermission("target-View", app_name="job")
@HasPermission("quick_exec-Add", app_name="job")
def workflow_job_options(request):
    return _job_catalog(request, include_targets=True)


def _job_permissions(user):
    grants = getattr(user, "permission", {})
    return grants.get("job", set()) if isinstance(grants, dict) else grants


@require_GET
@api_errors
@HasPermission("data-View")
@HasPermission("script_library-View", app_name="job")
def integration_job_catalog(request):
    return _job_catalog(request, include_targets=request.user.is_superuser or "target-View" in _job_permissions(request.user))


def _job_catalog(request, *, include_targets):
    if not apps.is_installed("apps.job_mgmt"):
        return WebUtils.response_error("当前环境未启用作业平台", status_code=503)
    from apps.job_mgmt.views.script import ScriptViewSet
    from apps.job_mgmt.views.target import TargetViewSet

    scripts = scoped_resources(request, ScriptViewSet).exclude(script_type="bat").values("id", "name", "description", "params")
    return WebUtils.response_success(
        {
            "can_execute": request.user.is_superuser or "quick_exec-Add" in _job_permissions(request.user),
            "scripts": [{**s, "params": public_params(s["params"])} for s in scripts if supports_params(s["params"])],
            "targets": list(scoped_resources(request, TargetViewSet).values("id", "name")) if include_targets else [],
        }
    )


def _form_fields(fields):
    for field in fields:
        if field.get("type") not in LAYOUT_ONLY:
            yield field
        if field.get("type") not in TABLE_FIELDS:
            yield from _form_fields(field.get("children") or [])


def upstream_outputs(node_id, predecessors, outputs):
    visited = {node_id}
    pending = list(predecessors[node_id])
    keys = set()
    while pending:
        parent = pending.pop()
        if parent in visited:
            continue
        visited.add(parent)
        if parent in outputs:
            keys.add(outputs[parent])
        pending.extend(predecessors[parent])
    return keys


def validate_job_sources(config, params, fields, outputs):
    mode = config.get("mode", "each" if config.get("table_key") else "once")
    collection = config.get("collection", f"form.{config.get('table_key')}" if config.get("table_key") else "")
    batch_size = config.get("batch_size")
    dispatch_mode = config.get("dispatch_mode", "batch" if batch_size else "parallel")
    if mode not in ("once", "each") or (mode == "once" and (collection or batch_size is not None)):
        raise ValueError("请选择有效的作业执行方式")
    if dispatch_mode not in {"batch", "parallel"} or (dispatch_mode == "parallel" and batch_size is not None):
        raise ValueError("并发执行不能配置每批项数")
    if dispatch_mode == "batch" and batch_size is None:
        raise ValueError("分批执行需要设置每批项数")
    if mode == "once" and "dispatch_mode" in config:
        raise ValueError("单次执行无需配置集合调度方式")
    if batch_size is not None and (type(batch_size) is not int or not 1 <= batch_size <= 100):
        raise ValueError("每批数量应为 1 至 100 的整数")
    source, _, key = collection.partition(".") if isinstance(collection, str) else ("", "", "")
    field = fields.get(key, {})
    field_type = field.get("type")
    if mode == "each" and not ((source == "form" and field_type in TABLE_FIELDS | LIST_TYPES) or (source == "output" and key in outputs)):
        raise ValueError("请选择有效的表单集合或上游输出")
    collection_types = TABLE_FIELDS | LIST_TYPES
    table_items = source == "form" and field_type in TABLE_FIELDS
    columns = (
        {col["key"] for col in configured_table_columns(field) if col.get("key") and col.get("type") not in collection_types}
        if table_items
        else set()
    )
    mapping = config.get("params", {})
    if (
        not isinstance(mapping, dict)
        or set(mapping) - {p["name"] for p in params}
        or any(p["is_required"] and p["name"] not in mapping for p in params)
    ):
        raise ValueError("请配置作业模板的必填参数")
    for name, value in mapping.items():
        if isinstance(value, str):
            value = {"source": "item", "key": value}
        if not isinstance(value, dict) or not isinstance(value.get("key"), str):
            raise ValueError(f"作业参数「{name}」缺少有效的取值来源")
        kind, key = value.get("source"), value["key"]
        if kind == "item" and mode == "each" and (source == "output" or (key in columns if table_items else not key)):
            continue
        if kind == "form" and key in fields and fields[key].get("type") not in collection_types:
            continue
        if kind == "output" and key in outputs:
            continue
        if kind == "literal" or kind == "system" and key in {"id", "sn", "title", "creator"}:
            continue
        raise ValueError(f"请检查作业参数「{name}」的字段来源或同行字段")


def validate_job_bindings(request, design):
    nodes = [node for node in design.get("nodes", []) if (node.get("auto") or {}).get("kind") == "job_template"]
    if not nodes:
        return
    if not apps.is_installed("apps.job_mgmt"):
        raise ValueError("当前环境未启用作业平台")
    from apps.job_mgmt.services.template_revision import payload_hash, script_payload
    from apps.job_mgmt.views.script import ScriptViewSet
    from apps.job_mgmt.views.target import TargetViewSet

    user = request.user
    grants = _job_permissions(user)
    if not user.is_superuser and not {"quick_exec-Add", "script_library-View", "target-View"}.issubset(grants):
        raise PermissionError
    scripts = scoped_resources(request, ScriptViewSet)
    targets = scoped_resources(request, TargetViewSet)
    fields = {f["key"]: f for f in _form_fields((design.get("form_schema") or {}).get("fields", []))}
    predecessors = defaultdict(list)
    for edge in design.get("edges", []):
        predecessors[edge["to"]].append(edge["from"])
    outputs = {
        n.get("id"): n["auto"]["result_field"]
        for n in design["nodes"]
        if (n.get("auto") or {}).get("kind") == "integration" and n["auto"].get("result_field")
    }
    for node in nodes:
        config = node["auto"]
        script = scripts.filter(pk=config.get("script_id")).first()
        target = targets.filter(pk=config.get("target_id")).first()
        if node.get("type") != "auto" or not script or not supports_params(script.params) or not target:
            raise ValueError("请选择当前组织有权使用的作业脚本和执行目标")
        if script.script_type not in ({"powershell"} if target.os_type == "windows" else {"shell", "python"}):
            raise ValueError("作业脚本类型与目标操作系统不匹配")
        validate_job_sources(config, public_params(script.params), fields, upstream_outputs(node.get("id"), predecessors, outputs))
        config["binding"] = {
            "operator": user.username,
            "team_id": int(get_current_team(request)),
            "script_hash": payload_hash(script_payload(script)),
        }
