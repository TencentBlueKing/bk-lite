# -- coding: utf-8 --
# @File: zabbix.py

from abc import ABC
from typing import Dict, Any, List

from apps.alerts.common.source_adapter.base import AlertSourceAdapter


class ZabbixAdapter(AlertSourceAdapter, ABC):
    """Zabbix 告警源适配器"""

    @staticmethod
    def _is_english(language: str | None) -> bool:
        return str(language or "").lower().startswith("en")

    def fetch_alerts(self) -> List[Dict[str, Any]]:
        return []

    def normalize_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = payload.get("events", [])
        if isinstance(events, list) and events:
            return events

        single_event = payload.get("event")
        if isinstance(single_event, dict):
            normalized_event = dict(single_event)
            if not normalized_event.get("external_id"):
                problem_id = (
                        normalized_event.get("problem_id")
                        or normalized_event.get("problemId")
                        or normalized_event.get("labels", {}).get("problem_id")
                )
                if not problem_id:
                    raise ValueError("Zabbix event missing ProblemId/external_id.")
                normalized_event["external_id"] = str(problem_id)

            if not normalized_event.get("action"):
                event_value = str(payload.get("EventValue") or normalized_event.get("event_value") or "").strip()
                normalized_event["action"] = "recovery" if event_value == "0" else "created"
            return [normalized_event]

        problem_id = payload.get("ProblemId") or payload.get("problem_id")
        if not problem_id:
            raise ValueError("Missing events problem_id.")

        event_value = str(payload.get("EventValue", "")).strip()
        return [
            {
                "title": payload.get("Subject") or payload.get("title") or "Zabbix Alert",
                "description": payload.get("Message") or payload.get("description"),
                "level": str(payload.get("Severity", "3")),
                "item": payload.get("TriggerName") or payload.get("item"),
                "start_time": payload.get("start_time"),
                "labels": {
                    "problem_id": str(problem_id),
                    "event_id": str(payload.get("EventId", "")),
                    "trigger_id": str(payload.get("TriggerId", "")),
                    "host_id": str(payload.get("HostId", "")),
                    "host_name": payload.get("HostName", ""),
                },
                "rule_id": payload.get("TriggerId"),
                "external_id": str(problem_id),
                "resource_id": str(payload.get("HostId", "")) or None,
                "resource_name": payload.get("HostName"),
                "resource_type": payload.get("ResourceType"),
                "action": "recovery" if event_value == "0" else "created",
                "service": payload.get("service"),
                "location": payload.get("location"),
                "tags": payload.get("Tags", {}),
            }
        ]

    def get_integration_guide(self, base_url: str, language: str | None = None) -> Dict[str, Any]:
        webhook_url = f"{base_url}/api/v1/alerts/api/source/{self.alert_source.source_id}/webhook/"
        is_english = self._is_english(language)
        script = f"""
var params = JSON.parse(value);
var isRecovery = String(params.EventValue) === \"0\";
var currentEventId = isRecovery
  ? String(params.RecoveryEventId || params.EventId || \"\")
  : String(params.EventId || \"\");

var payload = {{
  source_id: params.SOURCE_ID || \"{self.alert_source.source_id}\",
  event: {{
    external_id: String(params.ProblemId),
    title: params.Subject,
    description: params.Message,
    level: String(params.Severity || \"3\"),
    item: params.TriggerName,
    rule_id: params.TriggerId,
    resource_id: params.HostId,
    resource_name: params.HostName,
    resource_type: params.ResourceType || \"host\",
    action: isRecovery ? \"recovery\" : \"created\",
    labels: {{
      problem_id: String(params.ProblemId),
      event_id: currentEventId,
      trigger_id: String(params.TriggerId || \"\"),
      host_id: String(params.HostId || \"\"),
      host_name: params.HostName || \"\"
    }}
  }}
}};

var req = new HttpRequest();
req.addHeader(\"Content-Type: application/json\");
req.addHeader(\"SECRET: \" + (params.SECRET || \"{self.alert_source.secret}\"));

var resp = req.post(params.URL || \"{webhook_url}\", JSON.stringify(payload));

if (req.getStatus() < 200 || req.getStatus() >= 300) {{
  throw \"BK-Lite webhook failed. HTTP status: \" + req.getStatus() + \", response: \" + resp;
}}

return \"OK\";
""".strip()
        description = (
            "Confirm the BK-Lite interface requirements first, then configure the Zabbix Webhook Media Type, bind it to a user, and create an Action step by step. BK-Lite uses the Zabbix Webhook Media Type, and external_id must always use ProblemId."
            if is_english
            else "先确认 BK-Lite 接口要求，再按步骤在 Zabbix 中创建 Webhook Media Type、绑定用户并配置 Action。BK-Lite 使用 Zabbix Webhook Media Type 接入，external_id 固定使用 ProblemId。"
        )

        setup_steps = [
            {
                "title": "1. Determine the three BK-Lite values first" if is_english else "1. 先确定 BK-Lite 侧三个值",
                "items": [
                    "Get source_id, secret, and webhook_url from the BK-Lite Zabbix integration source first."
                    if is_english else "你先从 BK-Lite 的 Zabbix 集成源拿到 source_id、secret、webhook_url。",
                    (f"Current webhook_url: {webhook_url}" if is_english else f"当前 webhook_url 为：{webhook_url}"),
                    "If this source already exists in BK-Lite, the safest option is to call GET /api/v1/alerts/api/alert_source/{id}/integration-guide/ and use webhook_url, headers.SECRET, and script_template from the response."
                    if is_english else "如果 BK-Lite 已经有这条源，最稳的是直接调用 GET /api/v1/alerts/api/alert_source/{id}/integration-guide/，以返回值中的 webhook_url、headers.SECRET、script_template 为准。",
                ],
            },
            {
                "title": "2. Create a Media Type in Zabbix" if is_english else "2. 在 Zabbix 里创建 Media Type",
                "items": [
                    "Go to Alerts -> Media types -> Create media type."
                    if is_english else "进入 Alerts -> Media types -> Create media type。",
                    "Set Name to BK-Lite Webhook, Type to Webhook, and enable it."
                    if is_english else "Name 建议填写 BK-Lite Webhook，Type 选择 Webhook，Enabled 勾选。",
                    "The script must post to /api/source/{source_id}/webhook/; do not hand-build the path incorrectly."
                    if is_english else "后续脚本统一调用 /api/source/{source_id}/webhook/ 路径，不要手工拼错前缀。",
                ],
            },
            {
                "title": "3. Configure webhook parameters and script" if is_english else "3. 配置 Webhook 参数与脚本",
                "items": [
                    "In Parameters, configure URL, SECRET, SOURCE_ID, Subject, Message, Severity, TriggerName, ProblemId, EventId, RecoveryEventId, TriggerId, HostId, HostName, EventValue, and ResourceType."
                    if is_english else "建议在 Parameters 中配置 URL、SECRET、SOURCE_ID、Subject、Message、Severity、TriggerName、ProblemId、EventId、RecoveryEventId、TriggerId、HostId、HostName、EventValue、ResourceType。",
                    "Use webhook_url for URL, the BK-Lite secret for SECRET, and the BK-Lite source_id for SOURCE_ID."
                    if is_english else "其中 URL 填 webhook_url，SECRET 填 BK-Lite 的 secret，SOURCE_ID 填 BK-Lite 的 source_id。",
                    "ProblemId should use {EVENT.ID}; recovery must continue to point to the original ProblemId. EventValue should use {EVENT.VALUE}."
                    if is_english else "ProblemId 建议使用 {EVENT.ID}，Recovery 时也要继续指向原 ProblemId；EventValue 使用 {EVENT.VALUE}。",
                    "Use HttpRequest in the script to send application/json and build the payload from script_template."
                    if is_english else "脚本中使用 HttpRequest 发送 application/json 请求，并按 script_template 组装 payload。",
                ],
            },
            {
                "title": "4. Configure Message templates" if is_english else "4. 配置 Message templates",
                "items": [
                    "Even when you use a custom Webhook script, the Media Type still needs Problem and Recovery message templates."
                    if is_english else "即使使用自定义 Webhook 脚本，也需要为 Media Type 配置 Problem / Recovery 的 message templates。",
                    "For Problem, use Problem: {TRIGGER.NAME} as the Subject and include Host, Severity, Trigger, Event ID, and Time in the Message."
                    if is_english else "建议 Problem 模板使用 Problem: {TRIGGER.NAME} 作为 Subject，并在 Message 中包含 Host、Severity、Trigger、Event ID、Time。",
                    "For Recovery, use Recovery: {TRIGGER.NAME} as the Subject and include Host, Severity, Trigger, Problem Event ID, Recovery Event ID, and Recovery Time in the Message."
                    if is_english else "建议 Recovery 模板使用 Recovery: {TRIGGER.NAME} 作为 Subject，并在 Message 中包含 Host、Severity、Trigger、Problem Event ID、Recovery Event ID、Recovery Time。",
                ],
            },
            {
                "title": "5. Bind the Media to a user" if is_english else "5. 给用户绑定 Media",
                "items": [
                    "Go to Users -> Users -> target user -> Media -> Add."
                    if is_english else "进入 Users -> Users -> 目标用户 -> Media -> Add。",
                    "Choose the BK-Lite Webhook media type."
                    if is_english else "Type 选择刚创建的 BK-Lite Webhook。",
                    "Send to can be a placeholder such as bk-lite; keep default When active, enable all severities for now, and enable the entry."
                    if is_english else "Send to 可填写占位值，例如 bk-lite；When active 使用默认，Use if severity 建议先全部勾选，Enabled 勾选。",
                    "This step is required because Zabbix sends messages to users, not directly to a media type."
                    if is_english else "这个步骤不能省，Zabbix 的动作是发给用户，而不是直接发给 media type。",
                ],
            },
            {
                "title": "6. Create an Action" if is_english else "6. 创建 Action",
                "items": [
                    "Go to Alerts -> Actions -> Trigger actions -> Create action."
                    if is_english else "进入 Alerts -> Actions -> Trigger actions -> Create action。",
                    "You can keep Conditions broad at first for easier testing, for example Host group = test host group or Trigger name contains your test trigger name."
                    if is_english else "Conditions 可以先放宽一些，便于联调，例如 Host group = 测试主机组，或 Trigger name contains 测试 trigger 名。",
                    "In Operations, send the message to a user bound to BK-Lite Webhook, for example Send to Users: Admin and Send only to: BK-Lite Webhook."
                    if is_english else "在 Operations 中把消息发送给绑定了 BK-Lite Webhook 的用户，例如 Send to Users: Admin，Send only to: BK-Lite Webhook。",
                    "Configure the same send action in Recovery operations, otherwise you will only get created events and never recovery events."
                    if is_english else "Recovery operations 也要配置同样的发送动作，否则只会有 created，没有 recovery。",
                    "Problem and Recovery must use the same ProblemId so BK-Lite can correlate them."
                    if is_english else "这样 Problem 和 Recovery 都会推送到 BK-Lite；同时必须保证两次通知使用同一个 ProblemId。",
                ],
            },
        ]

        parameter_guidance = [
            {"name": "Interface requirements" if is_english else "接口要求", "required": True,
             "description": "Use POST with Content-Type: application/json and a SECRET header." if is_english else "请求方法使用 POST，请求头至少包含 Content-Type: application/json 和 SECRET。"},
            {"name": "webhook_url", "required": True,
             "description": "The URL must be /api/v1/alerts/api/source/{source_id}/webhook/, and source_id must match the BK-Lite source configuration." if is_english else "地址必须是 /api/v1/alerts/api/source/{source_id}/webhook/，其中 source_id 与 BK-Lite 中配置的一致。"},
            {"name": "SECRET", "required": True,
             "description": "The SECRET header must exactly match the secret stored in the BK-Lite alert source." if is_english else "Header 中 SECRET 的值必须与 BK-Lite 告警源中保存的 secret 完全一致。"},
            {"name": "SOURCE_ID", "required": True,
             "description": "Pass it explicitly as a script parameter and keep it consistent with the source_id in the URL." if is_english else "建议作为脚本参数显式传入，并与 URL 中的 source_id 保持一致。"},
            {"name": "ProblemId", "required": True,
             "description": "This is the recovery correlation key and must stay the same across both Problem and Recovery notifications." if is_english else "这是恢复闭环主键，Problem / Recovery 两次通知必须保持一致。"},
            {"name": "EventId", "required": True,
             "description": "Unique event identifier; keep it aligned with the original Zabbix event when possible." if is_english else "事件唯一标识，建议与原始 Zabbix 事件保持一致。"},
            {"name": "RecoveryEventId", "required": False,
             "description": "Recommended for Recovery so the recovery event ID is preserved." if is_english else "建议在 Recovery 场景传递，用于记录恢复事件 ID。"},
            {"name": "TriggerId", "required": True,
             "description": "Trigger ID used to locate the corresponding alert rule." if is_english else "触发器 ID，用于定位对应告警规则。"},
            {"name": "HostId", "required": True,
             "description": "Identifier of the alerting host." if is_english else "告警主机标识。"},
            {"name": "HostName", "required": True,
             "description": "Display name of the alerting host." if is_english else "告警主机名称。"},
            {"name": "Severity", "required": True,
             "description": "Use a numeric string where possible, for example 0/1/2/3." if is_english else "建议使用数字字符串，例如 0/1/2/3。"},
            {"name": "Subject", "required": True,
             "description": "Alert title used by BK-Lite as the event title." if is_english else "告警标题，BK-Lite 会用它生成 title。"},
            {"name": "Message", "required": True,
             "description": "Alert body used by BK-Lite as the event description." if is_english else "告警详情，BK-Lite 会用它生成 description。"},
            {"name": "EventValue", "required": True,
             "description": "Recovery must be 0; any other value is treated as created." if is_english else "Recovery 阶段必须为 0；其他值会被视为 created。"},
            {"name": "TriggerName", "required": False,
             "description": "Recommended so BK-Lite can show a readable item field." if is_english else "建议传递，便于在 BK-Lite 中展示 item。"},
            {"name": "ResourceType", "required": False,
             "description": "Recommended for additional resource type context." if is_english else "建议传递，便于补充资源类型信息。"},
        ]

        verification = {
            "curl_check": {
                "title": "CURL connectivity check" if is_english else "先做 CURL 打通",
                "summary": "Before enabling the real Zabbix Action, verify the webhook endpoint is reachable with a manual request."
                if is_english else "在切到 Zabbix Action 前，先验证 webhook 是否可达。",
                "expected_results": [
                    "HTTP returns 200.",
                    "A created event appears in BK-Lite.",
                ] if is_english else ["HTTP 返回 200。", "BK-Lite 中能看到 created 事件。"],
            },
            "problem_check": {
                "title": "Problem verification" if is_english else "再做真实 Problem 验证",
                "steps": [
                    "Trigger a Zabbix Problem.",
                    "Confirm the Action invoked the Webhook Media Type.",
                    "Confirm a created event appears in BK-Lite.",
                ] if is_english else [
                    "触发一个 Zabbix Problem。",
                    "确认 Action 已调用 Webhook Media Type。",
                    "在 BK-Lite 中确认 created 事件已生成。",
                ],
            },
            "recovery_check": {
                "title": "Recovery verification" if is_english else "恢复验证",
                "steps": [
                    "Recover the problem.",
                    "Confirm Zabbix sends the webhook again.",
                    "Confirm a recovery event appears in BK-Lite.",
                    "Verify created and recovery share the same external_id.",
                ] if is_english else [
                    "让问题恢复。",
                    "确认 Zabbix 再次发送 webhook。",
                    "在 BK-Lite 中确认 recovery 事件已生成。",
                    "核对 created / recovery 的 external_id 是否一致。",
                ],
            },
        }

        field_mappings = [
            {"bk_lite_field": "title",
             "zabbix_field": "Subject or event.title" if is_english else "Subject 或 event.title"},
            {"bk_lite_field": "description",
             "zabbix_field": "Message or event.description" if is_english else "Message 或 event.description"},
            {"bk_lite_field": "level",
             "zabbix_field": "Severity or event.level" if is_english else "Severity 或 event.level"},
            {"bk_lite_field": "item",
             "zabbix_field": "TriggerName or event.item" if is_english else "TriggerName 或 event.item"},
            {"bk_lite_field": "rule_id",
             "zabbix_field": "TriggerId or event.rule_id" if is_english else "TriggerId 或 event.rule_id"},
            {"bk_lite_field": "external_id",
             "zabbix_field": "ProblemId or event.external_id" if is_english else "ProblemId 或 event.external_id"},
            {"bk_lite_field": "resource_id",
             "zabbix_field": "HostId or event.resource_id" if is_english else "HostId 或 event.resource_id"},
            {"bk_lite_field": "resource_name",
             "zabbix_field": "HostName or event.resource_name" if is_english else "HostName 或 event.resource_name"},
            {"bk_lite_field": "action",
             "zabbix_field": "EventValue=0 -> recovery, otherwise -> created" if is_english else "EventValue=0 -> recovery，其他 -> created"},
        ]

        troubleshooting = [
            {
                "symptom": "Missing source_id returned" if is_english else "返回 Missing source_id",
                "cause": "The URL does not contain the correct source_id." if is_english else "URL 中没有正确带上 source_id。",
                "action": "Confirm you are using /api/source/{source_id}/webhook/." if is_english else "确认使用的是 /api/source/{source_id}/webhook/。",
            },
            {
                "symptom": "Invalid secret returned" if is_english else "返回 Invalid secret",
                "cause": "The SECRET header is incorrect." if is_english else "Header 中 SECRET 错误。",
                "action": "Re-check the secret configured on the BK-Lite alert source." if is_english else "对照 BK-Lite 告警源配置重新填写。",
            },
            {
                "symptom": "created exists but recovery is missing" if is_english else "created 有，recovery 没有",
                "cause": "ProblemId changed during recovery, or EventValue is not 0." if is_english else "ProblemId 在恢复阶段变化，或 EventValue 不是 0。",
                "action": "Make sure Recovery uses the same ProblemId and EventValue=0." if is_english else "确认 Recovery 使用同一个 ProblemId，且 EventValue=0。",
            },
        ]

        key_reminders = [
            "Confirm the interface requirements first: POST + application/json + SECRET." if is_english else "接口要求先确认：POST + application/json + SECRET。",
            "Always use /api/source/{source_id}/webhook/." if is_english else "统一使用 /api/source/{source_id}/webhook/。",
            "ProblemId must stay the same across both Problem and Recovery notifications." if is_english else "ProblemId 必须在 Problem / Recovery 两次通知中保持一致。",
        ]

        return {
            "source_type": self.alert_source.source_type,
            "source_id": self.alert_source.source_id,
            "webhook_url": webhook_url,
            "headers": {"SECRET": self.alert_source.secret},
            "description": description,
            "media_type_parameters": [
                "URL", "SECRET", "SOURCE_ID", "Subject", "Message", "Severity",
                "TriggerName", "ProblemId", "EventId", "RecoveryEventId", "TriggerId",
                "HostId", "HostName", "EventValue", "ResourceType"
            ],
            "setup_steps": setup_steps,
            "parameter_guidance": parameter_guidance,
            "verification": verification,
            "field_mappings": field_mappings,
            "troubleshooting": troubleshooting,
            "key_reminders": key_reminders,
            "script_template": script,
        }

    def test_connection(self) -> bool:
        return True

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        return True
