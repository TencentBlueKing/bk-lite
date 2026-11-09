from typing import Any

import requests

from apps.core.logger import itsm_logger


class FlowableError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"Flowable {status}")


class FlowableClient:
    """封装 Flowable 7.1 REST。上下文是 /flowable-rest/service，不是旧的 process-api。"""

    def __init__(self, base_url: str, username: str, password: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (username, password)

    def list_deployments(self) -> dict[str, Any]:
        return self._request("GET", "/flowable-rest/service/repository/deployments")

    def deploy_bpmn(self, name: str, xml: str) -> dict[str, Any]:
        response = self._raw(
            "POST",
            "/flowable-rest/service/repository/deployments",
            files={"file": (f"{name}.bpmn", xml, "text/xml")},
        )
        return response.json()

    def start_process(self, process_definition_key: str, business_key: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            "/flowable-rest/service/runtime/process-instances",
            json={"processDefinitionKey": process_definition_key, "businessKey": business_key, "variables": _variables(variables or {})},
        )

    def list_tasks(self, process_instance_id: str) -> dict[str, Any]:
        return self._request("GET", "/flowable-rest/service/runtime/tasks", params={"processInstanceId": process_instance_id})

    def complete_task(self, task_id: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(
            "POST", f"/flowable-rest/service/runtime/tasks/{task_id}", json={"action": "complete", "variables": _variables(variables or {})}
        )

    def get_process_instance(self, process_instance_id: str) -> dict[str, Any]:
        return self._request("GET", f"/flowable-rest/service/runtime/process-instances/{process_instance_id}")

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = self._raw(method, path, **kwargs)
        if not response.content:
            return {}
        return response.json()

    def _raw(self, method: str, path: str, **kwargs) -> requests.Response:
        last_error = None
        for _ in range(3):
            try:
                response = self.session.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                itsm_logger.warning("Flowable 请求失败: %s", type(exc).__name__)
                continue
            if response.status_code >= 500:
                last_error = FlowableError(response.status_code, response.text[:500])
                continue
            if response.status_code >= 400:
                raise FlowableError(response.status_code, response.text[:500])
            return response
        raise FlowableError(0, str(last_error))


def _variables(values: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for name, value in values.items():
        kind = "integer" if isinstance(value, int) and not isinstance(value, bool) else "boolean" if isinstance(value, bool) else "string"
        result.append({"name": name, "value": value if kind != "string" else str(value), "type": kind})
    return result
