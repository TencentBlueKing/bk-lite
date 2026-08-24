"""作业管理 NATS 模块目录查询。"""

from django.db import connection

from apps.job_mgmt.models import DangerousPath, DangerousRule, JobExecution, Playbook, ScheduledTask, Script, Target
from apps.job_mgmt.utils.team_authz import is_team_authorized, normalize_team


def get_module_list():
    return [
        {"name": "script", "display_name": "脚本库"},
        {"name": "playbook", "display_name": "Playbook库"},
        {"name": "target", "display_name": "目标"},
        {"name": "job_execution", "display_name": "作业执行"},
        {"name": "scheduled_task", "display_name": "定时任务"},
        {
            "name": "system",
            "display_name": "系统管理",
            "children": [
                {"name": "dangerous_rule", "display_name": "高危命令"},
                {"name": "dangerous_path", "display_name": "高危路径"},
            ],
        },
    ]


def _filter_by_team(queryset, group_id):
    if connection.features.supports_json_field_contains:
        return queryset.filter(team__contains=group_id)
    matched_ids = [item.id for item in queryset.only("id", "team") if group_id in normalize_team(item.team)]
    return queryset.filter(id__in=matched_ids)


def get_module_data(module, child_module, page, page_size, group_id, *, team=None):
    model_map = {
        "script": Script,
        "playbook": Playbook,
        "target": Target,
        "job_execution": JobExecution,
        "scheduled_task": ScheduledTask,
    }
    system_model_map = {"dangerous_rule": DangerousRule, "dangerous_path": DangerousPath}
    model = system_model_map.get(child_module) if module == "system" else model_map.get(module)
    if model is None:
        key = "child_module" if module == "system" else "module"
        value = child_module if module == "system" else module
        return {"result": False, "message": f"未知 {key}: {value}"}

    requested_teams = normalize_team(group_id)
    authorized_team_ids = normalize_team(team)
    if len(requested_teams) != 1:
        return {"result": False, "message": "group_id 参数非法"}
    if not authorized_team_ids:
        return {"result": False, "message": "team 不能为空"}
    group_id = next(iter(requested_teams))
    if not is_team_authorized(group_id, authorized_team_ids):
        return {"result": False, "message": "无权访问该团队数据"}
    try:
        page = max(1, int(page))
        page_size = max(1, int(page_size))
    except (TypeError, ValueError):
        return {"result": False, "message": "page/page_size 参数非法"}
    queryset = _filter_by_team(model.objects.all(), group_id)
    start = (page - 1) * page_size
    return {"count": queryset.count(), "items": list(queryset.values("id", "name")[start:start + page_size])}
