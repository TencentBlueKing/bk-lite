from __future__ import annotations

import time
from typing import Any, Callable

from apps.rpc.job_mgmt import JobMgmt

TERMINAL_STATUSES = {"success", "failed", "timeout", "cancelled", "canceled"}


class JobPlatformError(RuntimeError):
    pass


class JobPlatformExecutor:
    def __init__(self, client=None, *, sleep: Callable[[float], None] = time.sleep):
        self.client = client or JobMgmt(is_local_client=True)
        self.sleep = sleep

    @staticmethod
    def _actor_context(actor: dict[str, Any], team: int) -> dict[str, Any]:
        username = str(actor.get("username") or "").strip()
        if not username:
            raise JobPlatformError("作业执行缺少可信执行人快照")
        return {
            "username": username,
            "domain": str(actor.get("domain") or "domain.com"),
            "authorized_team_ids": [team],
        }

    def submit(
        self,
        *,
        name: str,
        nodes: list[dict[str, Any]],
        team: int,
        target_source: str,
        script_type: str,
        script_content: str,
        timeout: int,
        actor: dict[str, Any],
        params: list[dict[str, str]] | None = None,
        idempotency_key: str | None = None,
        workflow_execution_id: str | None = None,
    ) -> int:
        if target_source not in {"node_mgmt", "manual"}:
            raise JobPlatformError("不支持的作业目标来源")
        id_field = "node_id" if target_source == "node_mgmt" else "target_id"
        target_list = []
        for node in nodes:
            source_id = node.get("source_id")
            if source_id in (None, ""):
                raise JobPlatformError("作业目标缺少受控引用 ID")
            target_list.append(
                {
                    id_field: str(source_id) if target_source == "node_mgmt" else int(source_id),
                    "name": str(node.get("name", "")),
                    "ip": str(node.get("ip", "")),
                    "os": str(node.get("operating_system") or node.get("os_type") or ""),
                }
            )
        actor_context = self._actor_context(actor, team)
        payload = {
            "name": name[:100],
            "target_source": target_source,
            "target_list": target_list,
            "script_type": script_type,
            "script_content": script_content,
            "params": params or [],
            "timeout": max(30, min(int(timeout), 3600)),
            "team": [int(team)],
            "callback_type": "nats",
            "callback_subject": "bklite.workflow.job_result",
        }
        if idempotency_key:
            payload["idempotency_key"] = str(idempotency_key)[:255]
        if workflow_execution_id not in (None, ""):
            payload["workflow_execution_id"] = str(workflow_execution_id)[:64]
        response = (
            self.client.execute_automation_script(
                payload,
                actor_context,
            )
            or {}
        )
        if not response.get("result") or not (response.get("data") or {}).get("task_id"):
            raise JobPlatformError(str(response.get("message") or "作业平台拒绝了巡检任务"))
        return int(response["data"]["task_id"])

    def submit_file_distribute(
        self,
        *,
        name: str,
        nodes: list[dict[str, Any]],
        team: int,
        target_source: str,
        file_keys: list[str],
        target_path: str,
        timeout: int,
        actor: dict[str, Any],
        overwrite_strategy: str = "overwrite",
        idempotency_key: str | None = None,
        workflow_execution_id: str | None = None,
    ) -> int:
        if target_source not in {"node_mgmt", "manual"}:
            raise JobPlatformError("不支持的作业目标来源")
        if not file_keys:
            raise JobPlatformError("文件分发缺少文件")
        id_field = "node_id" if target_source == "node_mgmt" else "target_id"
        target_list = []
        for node in nodes:
            source_id = node.get("source_id")
            if source_id in (None, ""):
                raise JobPlatformError("作业目标缺少受控引用 ID")
            target_list.append(
                {
                    id_field: str(source_id) if target_source == "node_mgmt" else int(source_id),
                    "name": str(node.get("name", "")),
                    "ip": str(node.get("ip", "")),
                    "os": str(node.get("operating_system") or node.get("os_type") or ""),
                }
            )
        actor_context = self._actor_context(actor, team)
        payload = {
            "name": name[:100],
            "file_keys": [str(item) for item in file_keys],
            "target_source": target_source,
            "target_list": target_list,
            "target_path": str(target_path)[:512],
            "overwrite_strategy": overwrite_strategy if overwrite_strategy in {"overwrite", "skip"} else "overwrite",
            "timeout": max(30, min(int(timeout), 3600)),
            "team": [int(team)],
            "callback_type": "nats",
            "callback_subject": "bklite.workflow.job_result",
        }
        if idempotency_key:
            payload["idempotency_key"] = str(idempotency_key)[:255]
        if workflow_execution_id not in (None, ""):
            payload["workflow_execution_id"] = str(workflow_execution_id)[:64]
        response = self.client.execute_automation_file_distribute(payload, actor_context) or {}
        if not response.get("result") or not (response.get("data") or {}).get("task_id"):
            raise JobPlatformError(str(response.get("message") or "作业平台拒绝了文件分发任务"))
        return int(response["data"]["task_id"])

    def wait(self, task_id: int, *, team: int, timeout: int, actor: dict[str, Any]) -> dict[str, Any]:
        actor_context = self._actor_context(actor, team)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.client.get_automation_execution_statuses({"task_ids": [task_id]}, actor_context) or {}
            records = response.get("data") if response.get("result") else []
            status = records[0].get("status") if records else None
            if status in TERMINAL_STATUSES:
                detail = self.client.get_automation_execution_detail({"task_id": task_id}, actor_context) or {}
                if not detail.get("result"):
                    raise JobPlatformError(str(detail.get("message") or "无法读取作业详情"))
                return detail["data"]
            self.sleep(1)
        raise JobPlatformError("作业平台巡检任务等待超时")

    def cancel(self, task_id: int, *, authorized_team_ids: list[int], actor: dict[str, Any]) -> dict[str, Any]:
        username = str(actor.get("username") or "").strip()
        if not username:
            raise JobPlatformError("作业取消缺少可信执行人快照")
        teams = [int(team) for team in authorized_team_ids]
        if not teams:
            raise JobPlatformError("作业取消缺少组织边界")
        actor_context = {
            "username": username,
            "domain": str(actor.get("domain") or "domain.com"),
            "authorized_team_ids": teams,
        }
        response = self.client.cancel_automation_execution({"task_id": int(task_id)}, actor_context) or {}
        if not response.get("result"):
            raise JobPlatformError(str(response.get("message") or "作业平台拒绝了取消请求"))
        data = response.get("data") or {}
        if not isinstance(data, dict):
            raise JobPlatformError("作业平台取消响应非法")
        return data
