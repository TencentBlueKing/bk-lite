# -- coding: utf-8 --
# @File: zabbix.py

from abc import ABC
from typing import Dict, Any, List

from apps.alerts.common.source_adapter.base import AlertSourceAdapter
from apps.alerts.error import AuthenticationSourceError


class ZabbixAdapter(AlertSourceAdapter, ABC):
    """Zabbix 告警源适配器"""

    def authenticate(self) -> bool:
        if self.secret == self.alert_source.secret:
            return True
        raise AuthenticationSourceError("Authentication failed")

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

    def get_integration_guide(self, base_url: str) -> Dict[str, Any]:
        webhook_url = f"{base_url}/api/v1/alerts/api/source/{self.alert_source.source_id}/webhook/"
        script = f"""
var params = JSON.parse(value);
var isRecovery = String(params.EventValue) === \"0\";
var payload = {{
  source_id: \"{self.alert_source.source_id}\",
  event: {{
    external_id: String(params.ProblemId),
    title: params.Subject,
    description: params.Message,
    level: String(params.Severity || \"3\"),
    item: params.TriggerName,
    rule_id: params.TriggerId,
    resource_id: params.HostId,
    resource_name: params.HostName,
    resource_type: params.ResourceType || \"\",
    action: isRecovery ? \"recovery\" : \"created\",
    labels: {{
      problem_id: String(params.ProblemId),
      event_id: String(params.EventId || \"\"),
      trigger_id: String(params.TriggerId || \"\"),
      host_id: String(params.HostId || \"\"),
      host_name: params.HostName || \"\"
    }}
  }}
}};

var req = new HttpRequest();
req.addHeader(\"Content-Type: application/json\");
req.addHeader(\"SECRET: {self.alert_source.secret}\");
req.post(\"{webhook_url}\", JSON.stringify(payload));
return \"OK\";
""".strip()
        return {
            "source_type": self.alert_source.source_type,
            "source_id": self.alert_source.source_id,
            "webhook_url": webhook_url,
            "headers": {"SECRET": self.alert_source.secret},
            "description": "使用 Zabbix Webhook Media Type 对接 BK-Lite，external_id 固定使用 ProblemId。",
            "media_type_parameters": [
                "BKLiteURL", "Secret", "SourceId", "ProblemId", "EventId", "TriggerId",
                "HostId", "HostName", "Severity", "Subject", "Message", "EventValue"
            ],
            "script_template": script,
        }

    def test_connection(self) -> bool:
        return True

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        return True