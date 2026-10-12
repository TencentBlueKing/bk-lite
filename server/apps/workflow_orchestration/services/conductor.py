from __future__ import annotations

import hashlib
import json
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


class ExecutionStartUnknown(ConductorUnavailable):
    """Engine start outcome is unknown; local execution must be reconciled, not retried blindly."""

    def __init__(self, execution, message: str = "Conductor 启动结果未知，禁止盲重试"):
        self.execution = execution
        super().__init__(message)


def workflow_definition_digest(definition: dict[str, Any]) -> str:
    """Stable digest for immutable publish conflict checks."""

    payload = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _comparable_workflow_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Keep fields that identify an immutable published workflow body."""

    return {
        "name": definition.get("name"),
        "version": definition.get("version"),
        "tasks": definition.get("tasks") or [],
        "inputParameters": definition.get("inputParameters") or [],
        "outputParameters": definition.get("outputParameters") or {},
        "variables": definition.get("variables") or {},
        "timeoutSeconds": definition.get("timeoutSeconds"),
        "timeoutPolicy": definition.get("timeoutPolicy"),
        "restartable": definition.get("restartable"),
        "workflowStatusListenerEnabled": definition.get("workflowStatusListenerEnabled"),
    }


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

    def get_workflow_definition(self, name: str, version: int) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/metadata/workflow/{name}", params={"version": version}).json()
        except ConductorUnavailable:
            return None

    def register_workflow(self, definition: dict[str, Any]) -> None:
        try:
            self._request("POST", "/metadata/workflow", json=definition)
            return
        except ConductorConflict:
            pass
        # Compensate only when the existing engine definition matches our immutable digest.
        # Never PUT-overwrite a same name/version that carries different content.
        existing = self.get_workflow_definition(str(definition.get("name") or ""), int(definition.get("version") or 0))
        if existing is None:
            raise ConductorConflict("Conductor 流程版本已存在，但无法核对内容摘要")
        expected = workflow_definition_digest(_comparable_workflow_definition(definition))
        actual = workflow_definition_digest(_comparable_workflow_definition(existing))
        if expected != actual:
            raise ConductorConflict("Conductor 流程版本已存在且内容不一致，禁止覆盖")

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

    def find_workflow_ids_by_correlation_id(self, correlation_id: str) -> list[str]:
        """Best-effort lookup for start reconciliation; empty when the engine cannot confirm."""

        correlation_id = str(correlation_id or "").strip()
        if not correlation_id:
            return []
        try:
            payload = self._request(
                "GET",
                "/workflow/search",
                params={"query": f'correlationId="{correlation_id}"', "size": 5},
            ).json()
        except ConductorUnavailable:
            return []
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        workflow_ids: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            workflow_id = item.get("workflowId") or item.get("workflowID")
            if workflow_id not in (None, ""):
                workflow_ids.append(str(workflow_id))
        return workflow_ids

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
