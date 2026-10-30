import json
import re
from urllib.parse import urlsplit

from django.conf import settings

MAX_INPUT_BYTES = 65536
MAX_BINDINGS = 64

# 原生 ITSM OpenAPI（网关 /openapi/v1/itsm/openapi/v1）。CustomRenderer 把工单对象放在 data 根上。
# end_at 有值只表示工单已结束，用于展示「工单已关闭」，不关闭告警。
BKLITE_RESPONSE_CONTRACT = {
    "create_id_path": "id",
    "detail_fields": {
        "id": "id",
        "status": "status",
        "title": "title",
        "number": "sn",
        "end_at": "end_at",
        "label": "status_display",
    },
}


def response_contract_ready():
    try:
        validate_response_contract(BKLITE_RESPONSE_CONTRACT)
    except ItsmError:
        return False
    return True


class ItsmError(Exception):
    """只携带受控摘要，不能包含外部响应或认证信息。"""

    def __init__(self, message, outcome="config_error"):
        super().__init__(message)
        self.outcome = outcome


def connections(teams=None):
    configured = getattr(settings, "ALERT_ITSM_CONNECTIONS", None)
    if configured is not None:
        if not isinstance(configured, dict):
            raise ItsmError("ITSM 连接配置格式错误")
        return configured
    from apps.alerts.models.itsm import AlertItsmIntegration

    if not teams:
        return {}
    return {item.reference: item.connection_config() for item in AlertItsmIntegration.objects.filter(enabled=True, team_id__in=teams)}


def get_connection(reference, teams, instance_id=None, *, lock=False):
    configured = getattr(settings, "ALERT_ITSM_CONNECTIONS", None)
    if configured is not None:
        value = connections().get(reference)
    else:
        from apps.alerts.models.itsm import AlertItsmIntegration

        value = None
        if isinstance(reference, str) and reference.startswith("integration:") and reference[12:].isdigit():
            queryset = AlertItsmIntegration.objects.filter(pk=int(reference[12:]), enabled=True, team_id__in=teams)
            item = (queryset.select_for_update() if lock else queryset).first()
            value = item.connection_config() if item else None
    value = validate_connection(value, teams, instance_id)
    validate_response_contract(value)
    return value


def validate_connection(value, teams, instance_id=None):
    if not isinstance(value, dict) or not teams or not set(map(str, teams)).issubset(set(map(str, value.get("teams", [])))):
        raise ItsmError("ITSM 连接不存在或团队无权使用")
    parsed = urlsplit(value.get("url", ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ItsmError("ITSM 连接必须为部署配置的 HTTPS 地址")
    if (
        not isinstance(value.get("instance_id"), str)
        or not 1 <= len(value["instance_id"]) <= 100
        or (instance_id and value["instance_id"] != instance_id)
    ):
        raise ItsmError("ITSM 实例标识无效或已变更")
    return value


def validate_response_contract(value):
    detail = value.get("detail_fields")
    if not value.get("create_id_path") or not isinstance(detail, dict) or not detail.get("id") or not detail.get("status"):
        raise ItsmError("ITSM 工单接口联调尚未完成，暂不能配置建单规则或执行工单联动；不影响连接配置启用")
    paths = [value["create_id_path"], detail["id"], detail["status"]]
    paths += [detail[key] for key in ("title", "number", "end_at", "label") if key in detail]
    if any(not isinstance(path, str) or not re.fullmatch(r"[\w.-]{1,128}", path) for path in paths):
        raise ItsmError("ITSM 响应字段映射格式错误")


def validate_config(config, teams, *, lock_connection=False):
    if not isinstance(config, dict) or set(config) - {"connection", "workflow_key", "form_bindings", "close_alert_on_ticket_closed"}:
        raise ItsmError("ITSM 动作配置包含不支持的字段")
    reference = config.get("connection")
    workflow = config.get("workflow_key")
    if not isinstance(reference, str) or not reference or len(reference) > 100:
        raise ItsmError("请选择 ITSM 连接")
    if not isinstance(workflow, str) or not workflow.strip() or len(workflow) > 200:
        raise ItsmError("流程标识必填且不能超过 200 字符")
    if not isinstance(config.get("close_alert_on_ticket_closed", False), bool):
        raise ItsmError("关闭告警开关必须为布尔值")
    bindings = config.get("form_bindings")
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= MAX_BINDINGS:
        raise ItsmError("表单映射必须包含 1 至 64 个字段")
    names = set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) - {"name", "from", "value"}:
            raise ItsmError("表单字段映射格式错误")
        name = binding.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[\w.-]{1,128}", name) or name in names:
            raise ItsmError("表单字段名非法或重复")
        names.add(name)
        if binding.get("from") not in {"const", "field"} or "value" not in binding:
            raise ItsmError("表单映射仅支持常量或告警字段")
        if binding["from"] == "field":
            from apps.alerts.action.payload import TOP_FIELDS
            from apps.alerts.notification_templates.events import EVENT_JSON_ROOTS, EVENT_SCALAR_FIELDS

            path = binding["value"]
            scalar_fields = set(TOP_FIELDS) | {"source_names", "source_id"} | {f"event.{field}" for field in EVENT_SCALAR_FIELDS}
            prefixes = ("labels.", "enrichment.") + tuple(f"event.{root}." for root in EVENT_JSON_ROOTS)
            if not isinstance(path, str) or len(path) > 256 or not (path in scalar_fields or path.startswith(prefixes)):
                raise ItsmError("请选择允许传递的告警字段")
    if "ticket__title" not in names:
        raise ItsmError("必须配置 ticket__title 标题映射")
    if len(json.dumps(config).encode()) > MAX_INPUT_BYTES:
        raise ItsmError("表单配置超过 64 KiB")
    return get_connection(reference, teams, lock=lock_connection)


def form_data(config, snapshot):
    result = {}
    for binding in config["form_bindings"]:
        value = binding["value"] if binding["from"] == "const" else snapshot.get(binding["value"])
        if value is None:
            raise ItsmError("表单映射所需告警字段缺失")
        result[binding["name"]] = value
    if not isinstance(result["ticket__title"], str) or not result["ticket__title"].strip():
        raise ItsmError("工单标题必须为非空文本")
    if len(json.dumps(result).encode()) > MAX_INPUT_BYTES:
        raise ItsmError("建单表单超过 64 KiB")
    return result
