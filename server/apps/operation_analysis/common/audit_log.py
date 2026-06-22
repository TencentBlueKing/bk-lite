from rest_framework.response import Response

from apps.system_mgmt.utils.operation_log_utils import log_operation

OPS_ANALYSIS_APP = "ops-analysis"
IMPORT_OBJECT_TYPE_LABELS = {
    "namespace": "命名空间",
    "datasource": "数据源",
    "data_source": "数据源",
    "dashboard": "仪表盘",
    "topology": "拓扑图",
    "architecture": "架构图",
}
IMPORT_STATUS_ACTIONS = {
    "success": ("create", "新增"),
    "overwritten": ("update", "更新"),
}


def log_ops_analysis_operation(request, action_type, summary):
    return log_operation(request, action_type, OPS_ANALYSIS_APP, summary)


def log_ops_analysis_success(request, response, action_type, summary):
    if _is_success_response(response):
        log_ops_analysis_operation(request, action_type, summary)


def log_ops_analysis_import_results(request, results):
    if not isinstance(results, list):
        return

    for result in results:
        if not isinstance(result, dict):
            continue

        status_action = IMPORT_STATUS_ACTIONS.get(result.get("status"))
        if not status_action:
            continue

        action_type, action_label = status_action
        object_type = result.get("object_type")
        object_label = IMPORT_OBJECT_TYPE_LABELS.get(object_type, object_type or "对象")
        object_key = result.get("object_key") or result.get("new_id") or ""
        log_ops_analysis_operation(request, action_type, f"导入{action_label}{object_label}: {object_key}")


def get_response_name(response, fallback=""):
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        if data.get("name"):
            return data["name"]
        nested_data = data.get("data")
        if isinstance(nested_data, dict) and nested_data.get("name"):
            return nested_data["name"]
    return fallback


def _is_success_response(response):
    if not isinstance(response, Response):
        return False
    status_code = getattr(response, "status_code", 0)
    return 200 <= status_code < 300
