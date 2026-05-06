# -- coding: utf-8 --
# @File: prometheus.py
# @Time: 2025/5/13 15:57
# @Author: windyzhao

import requests
from datetime import datetime
from urllib.parse import urljoin
from typing import Dict, Any, List

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.alerts.common.source_adapter.base import AlertSourceAdapter
from apps.alerts.error import AuthenticationSourceError

from apps.alerts.common.source_adapter import logger


class PrometheusAdapter(AlertSourceAdapter):
    """Prometheus告警源适配器"""

    def authenticate(self) -> bool:
        if self.secret == self.alert_source.secret:
            return True
        raise AuthenticationSourceError("Authentication failed")

    def fetch_alerts(self) -> List[Dict[str, Any]]:
        base_url = self.config.get('base_url')
        api_path = self.config.get('api_path', '/api/v1/alerts')
        url = urljoin(base_url, api_path)

        try:
            response = requests.get(
                url,
                timeout=self.config.get('timeout', 10),
                verify=self.config.get('verify_ssl', True)
            )
            response.raise_for_status()
            return response.json().get('data', {}).get('alerts', [])
        except Exception as e:
            logger.error(f"Failed to fetch alerts from Prometheus: {e}")
            return []

    def normalize_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = payload.get("events", [])
        if isinstance(events, list) and events:
            return events

        alerts = payload.get("alerts", [])
        if not isinstance(alerts, list) or not alerts:
            raise ValueError("Missing events.")

        common_labels = payload.get("commonLabels", {}) or {}
        common_annotations = payload.get("commonAnnotations", {}) or {}
        receiver = payload.get("receiver")
        normalized_events = []

        for alert in alerts:
            labels = {**common_labels, **(alert.get("labels", {}) or {})}
            annotations = {**common_annotations, **(alert.get("annotations", {}) or {})}
            alertname = labels.get("alertname") or annotations.get("alertname") or "Prometheus Alert"
            resource_name = (
                labels.get("instance")
                or labels.get("pod")
                or labels.get("node")
                or labels.get("service")
                or labels.get("job")
            )
            external_id = self._build_external_id(labels, alert)
            data = {
                    "title": alertname if not resource_name else f"{alertname} ({resource_name})",
                    "description": annotations.get("description") or annotations.get("summary") or alertname,
                    "level": self._map_prometheus_severity(labels.get("severity")),
                    "item": alertname,
                    "start_time": self._iso_to_timestamp(alert.get("startsAt")),
                    "end_time": self._iso_to_timestamp(alert.get("endsAt")),
                    "labels": labels,
                    "rule_id": alertname,
                    "push_source_id": receiver,
                    "resource_name": resource_name,
                    "resource_id": resource_name,
                    "resource_type": labels.get("resource_type"),
                    "action": self._map_prometheus_status(alert.get("status")),
                    "service": labels.get("service") or labels.get("job"),
                    "location": labels.get("cluster") or labels.get("region"),
                    "tags": labels.get("tags", {}),
                }
            if external_id:
                data["external_id"] = external_id

            normalized_events.append(data)

        return normalized_events

    def get_integration_guide(self, base_url: str) -> Dict[str, Any]:
        webhook_url = f"{base_url}/api/v1/alerts/api/source/{self.alert_source.source_id}/webhook/"
        custom_payload_template = f"""
route:
  receiver: bk-lite-prometheus

receivers:
  - name: bk-lite-prometheus
    webhook_configs:
      - url: {webhook_url}
        send_resolved: true
        http_config:
          http_headers:
            SECRET:
              values: [\"{self.alert_source.secret}\"]
        payload:
          source_id: \"{self.alert_source.source_id}\"
          events: '{{{{ .Alerts | toJson }}}}'
""".strip()
        return {
            "source_type": self.alert_source.source_type,
            "source_id": self.alert_source.source_id,
            "webhook_url": webhook_url,
            "headers": {"SECRET": self.alert_source.secret},
            "modes": ["default_payload", "custom_payload"],
            "description": "兼容 Alertmanager 默认 webhook payload，并支持显式 external_id 的 custom payload。",
            "alertmanager_default_config": {
                "receiver": "bk-lite-prometheus-default",
                "webhook_configs": [
                    {
                        "url": webhook_url,
                        "send_resolved": True,
                        "http_config": {
                            "http_headers": {
                                "SECRET": {
                                    "values": [self.alert_source.secret],
                                }
                            }
                        },
                    }
                ],
            },
            "custom_payload_template": custom_payload_template,
        }

    def test_connection(self) -> bool:
        base_url = self.config.get('base_url')
        api_path = self.config.get('api_path', '/api/v1/targets')
        url = urljoin(base_url, api_path)

        try:
            response = requests.get(
                url,
                timeout=self.config.get('timeout', 10),
                verify=self.config.get('verify_ssl', True)
            )
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        required_fields = ['base_url']
        return all(field in config for field in required_fields)

    def _map_prometheus_severity(self, severity: str) -> str:
        severity = str(severity or "").lower()
        severity_map = {
            'critical': '0',
            'high': '0',
            'warning': '1',
            'info': '2',
            'none': '3',
        }
        return str(severity_map.get(severity, '3'))

    def _map_prometheus_status(self, status: str) -> str:
        status_map = {
            'firing': 'created',
            'resolved': 'recovery'
        }
        return status_map.get(str(status or '').lower(), 'created')

    def _build_external_id(self, labels: Dict[str, Any], alert: Dict[str, Any]) -> str:
        explicit_external_id = alert.get("external_id") or labels.get("external_id")
        if explicit_external_id:
            return str(explicit_external_id)
        return None

    @staticmethod
    def _iso_to_timestamp(value: str):
        if not value:
            return None

        parsed = parse_datetime(value)
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None

        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return str(int(parsed.timestamp()))
