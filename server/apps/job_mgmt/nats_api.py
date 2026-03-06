"""Job Management NATS API - 用于数据权限规则"""

import nats_client
from apps.job_mgmt.models import DangerousPath, DangerousRule, JobExecution, Playbook, ScheduledTask, Script, Target


@nats_client.register
def get_job_mgmt_module_list():
    """获取作业管理模块列表"""
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


@nats_client.register
def get_job_mgmt_module_data(module, child_module, page, page_size, group_id):
    """获取作业管理模块数据"""
    model_map = {
        "script": Script,
        "playbook": Playbook,
        "target": Target,
        "job_execution": JobExecution,
        "scheduled_task": ScheduledTask,
    }
    system_model_map = {
        "dangerous_rule": DangerousRule,
        "dangerous_path": DangerousPath,
    }

    if module != "system":
        model = model_map[module]
    else:
        model = system_model_map[child_module]

    queryset = model.objects.filter(team__contains=int(group_id))

    # 计算总数
    total_count = queryset.count()

    # 计算分页
    start = (page - 1) * page_size
    end = page * page_size

    # 获取当前页的数据
    data_list = queryset.values("id", "name")[start:end]

    return {
        "count": total_count,
        "items": list(data_list),
    }
