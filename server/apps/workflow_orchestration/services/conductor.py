from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import httpx


class ConductorConfigurationError(ValueError):
    pass


class ConductorUnavailable(RuntimeError):
    pass


class ConductorConflict(RuntimeError):
    pass


class ConductorClient:
    def __init__(self, base_url: str | None = None, *, transport=None, timeout: float = 10.0):
        raw_url = (base_url or os.getenv("CONDUCTOR_BASE_URL", "http://127.0.0.1:8091/api")).rstrip("/")
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ConductorConfigurationError("CONDUCTOR_BASE_URL 必须是安全的 http(s) 服务地址")
        if parsed.query or parsed.fragment or not parsed.path.endswith("/api"):
            raise ConductorConfigurationError("CONDUCTOR_BASE_URL 必须以 /api 结尾且不能包含查询参数")
        headers = {"Accept": "application/json"}
        token = os.getenv("CONDUCTOR_AUTH_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.base_url = raw_url
        self.health_url = raw_url[: -len("/api")] + "/health"
        # Conductor 是平台内部执行引擎；不应被开发机或容器的 HTTP(S)_PROXY 劫持。
        self._client = httpx.Client(timeout=timeout, transport=transport, headers=headers, trust_env=False)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 409:
                raise ConductorConflict("Conductor 流程版本已存在") from error
            raise ConductorUnavailable("Conductor 服务不可用或拒绝了请求") from error
        except httpx.HTTPError as error:
            raise ConductorUnavailable("Conductor 服务不可用或拒绝了请求") from error

    def health(self) -> dict[str, Any]:
        try:
            response = self._client.get(self.health_url)
            response.raise_for_status()
            data = response.json() if response.content else {}
            return {"healthy": True, "details": data}
        except (httpx.HTTPError, ValueError):
            return {"healthy": False, "details": {}}

    def register_task_definitions(self, definitions: list[dict[str, Any]]) -> None:
        self._request("POST", "/metadata/taskdefs", json=definitions)

    def register_workflow(self, definition: dict[str, Any]) -> None:
        try:
            self._request("POST", "/metadata/workflow", json=definition)
        except ConductorConflict:
            # 允许补偿「Conductor 已登记、BK-Lite 版本事务未落库」的部分成功。
            self._request("PUT", "/metadata/workflow", json=[definition])

    def start_workflow(self, name: str, *, version: int, inputs: dict[str, Any], correlation_id: str = "") -> str:
        response = self._request(
            "POST",
            f"/workflow/{name}",
            params={"version": version, "correlationId": correlation_id},
            json=inputs,
        )
        return response.text.strip().strip('"')

    def get_execution(self, workflow_id: str) -> dict[str, Any]:
        return self._request("GET", f"/workflow/{workflow_id}", params={"includeTasks": "true"}).json()

    def retry_workflow(self, workflow_id: str) -> None:
        self._request("POST", f"/workflow/{workflow_id}/retry")

    def restart_workflow(self, workflow_id: str) -> None:
        self._request("POST", f"/workflow/{workflow_id}/restart", params={"useLatestDefinitions": "false"})

    def terminate_workflow(self, workflow_id: str, *, reason: str) -> None:
        self._request("DELETE", f"/workflow/{workflow_id}", params={"reason": reason})

    def rerun_workflow(self, workflow_id: str, *, task_id: str = "", correlation_id: str = "") -> str:
        payload = {"reRunFromWorkflowId": workflow_id, "correlationId": correlation_id}
        if task_id:
            payload["reRunFromTaskId"] = task_id
        response = self._request("POST", f"/workflow/{workflow_id}/rerun", json=payload)
        return response.text.strip().strip('"')

    def poll_task(self, task_type: str, worker_id: str) -> dict[str, Any] | None:
        response = self._request("GET", f"/tasks/poll/{task_type}", params={"workerid": worker_id})
        if not response.content:
            return None
        result = response.json()
        return result or None

    def update_task(self, task_result: dict[str, Any]) -> None:
        self._request("POST", "/tasks", json=task_result)

    def complete_task(
        self,
        *,
        workflow_id: str,
        task_id: str,
        output: dict[str, Any],
        worker_id: str = "bklite-human",
    ) -> None:
        self.update_task(
            {
                "workflowInstanceId": workflow_id,
                "taskId": task_id,
                "workerId": worker_id,
                "status": "COMPLETED",
                "outputData": output,
            }
        )
