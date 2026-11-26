"""流程设计器通过作业平台的资源权限查询可绑定的脚本和执行目标。"""

from django.apps import apps
from django.views.decorators.http import require_GET
from rest_framework.exceptions import PermissionDenied

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.core.utils.web_utils import WebUtils
from apps.itsm.services.form.table_columns import TABLE_FIELDS, configured_table_columns
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


def _tables(fields):
    for field in fields:
        if field.get("type") in TABLE_FIELDS:
            yield field
        else:
            yield from _tables(field.get("children") or [])


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
    tables = {f["key"]: f for f in _tables((design.get("form_schema") or {}).get("fields", []))}
    for node in nodes:
        config = node["auto"]
        script = scripts.filter(pk=config.get("script_id")).first()
        target = targets.filter(pk=config.get("target_id")).first()
        if node.get("type") != "auto" or not script or not supports_params(script.params) or not target:
            raise ValueError("请选择当前组织有权使用的作业脚本和执行目标")
        if script.script_type not in ({"powershell"} if target.os_type == "windows" else {"shell", "python"}):
            raise ValueError("作业脚本类型与目标操作系统不匹配")
        table = tables.get(config.get("table_key"))
        if table is None:
            raise ValueError("请选择逐行执行的子表单")
        columns = {column.get("key") for column in configured_table_columns(table)}
        params = public_params(script.params)
        mapping = config.get("params", {})
        if (
            not isinstance(mapping, dict)
            or set(mapping) - {p["name"] for p in params}
            or any(not isinstance(value, str) or value not in columns for value in mapping.values())
            or any(p["is_required"] and p["name"] not in mapping for p in params)
        ):
            raise ValueError("请将作业必填参数映射到所选子表单的同行字段")
        config["binding"] = {
            "operator": user.username,
            "team_id": int(get_current_team(request)),
            "script_hash": payload_hash(script_payload(script)),
        }
