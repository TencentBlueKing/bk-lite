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

    def deploy_dmn(self, name: str, xml: str) -> dict[str, Any]:
        response = self._raw(
            "POST",
            "/flowable-rest/dmn-api/dmn-repository/deployments",
            files={"file": (f"{name}.dmn", xml, "text/xml")},
        )
        return response.json()

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

    def list_tasks_including_children(self, process_instance_id: str) -> list[dict[str, Any]]:
        items = list(self.list_tasks(process_instance_id).get("data") or [])
        children = self._request(
            "GET",
            "/flowable-rest/service/runtime/process-instances",
            params={"superProcessInstanceId": process_instance_id},
        )
        for child in children.get("data") or []:
            child_id = str(child.get("id") or "")
            if child_id:
                items.extend(self.list_tasks(child_id).get("data") or [])
        return items

    def complete_task(self, task_id: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(
            "POST", f"/flowable-rest/service/runtime/tasks/{task_id}", json={"action": "complete", "variables": _variables(variables or {})}
        )

    def update_task_assignee(self, task_id: str, assignee: str) -> dict[str, Any]:
        return self._request("PUT", f"/flowable-rest/service/runtime/tasks/{task_id}", json={"assignee": assignee})

    def change_state(self, process_instance_id: str, cancel_activity_ids: list[str], start_activity_ids: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/flowable-rest/service/runtime/process-instances/{process_instance_id}/change-state",
            json={"cancelActivityIds": cancel_activity_ids, "startActivityIds": start_activity_ids},
        )

    def acquire_jobs(self, topic: str, worker_id: str = "itsm") -> list[dict[str, Any]]:
        payload = self._request(
            "POST",
            "/flowable-rest/external-job-api/acquire/jobs",
            json={"workerId": worker_id, "topic": topic, "lockDuration": "PT1M", "numberOfTasks": 5},
        )
        if isinstance(payload, list):
            return payload
        return list(payload.get("data") or [])

    def complete_external_job(self, job_id: str, worker_id: str = "itsm", variables: dict | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/flowable-rest/external-job-api/acquire/jobs/{job_id}/complete",
            json={"workerId": worker_id, "variables": _variables(variables or {})},
        )

    def set_process_suspended(self, process_instance_id: str, suspended: bool) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/flowable-rest/service/runtime/process-instances/{process_instance_id}",
            json={"action": "suspend" if suspended else "activate"},
        )

    def delete_process_instance(self, process_instance_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/flowable-rest/service/runtime/process-instances/{process_instance_id}")

    def get_process_instance(self, process_instance_id: str) -> dict[str, Any]:
        return self._request("GET", f"/flowable-rest/service/runtime/process-instances/{process_instance_id}")

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = self._raw(method, path, **kwargs)
        if not response.content:
            return {}
        return response.json()

    def _raw(self, method: str, path: str, **kwargs) -> requests.Response:
        last_error = None
        # 写请求超时不代表引擎未执行，禁止无幂等键重放。
        for _ in range(3 if method.upper() in {"GET", "HEAD"} else 1):
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
        if isinstance(last_error, FlowableError):
            raise last_error
        raise FlowableError(0, str(last_error))


def _variables(values: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for name, value in values.items():
        if isinstance(value, bool):
            kind, stored = "boolean", value
        elif isinstance(value, int):
            kind, stored = "integer", value
        elif isinstance(value, float):
            kind, stored = "double", value
        elif isinstance(value, (list, dict)):
            kind, stored = "json", value
        else:
            kind, stored = "string", "" if value is None else str(value)
        result.append({"name": name, "value": stored, "type": kind})
    return result
