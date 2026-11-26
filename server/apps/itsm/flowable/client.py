from typing import Any

import requests

from apps.core.logger import itsm_logger


class FlowableError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"Flowable {status}")


class NoStartedInstance(FlowableError):
    def __init__(self):
        super().__init__(409, "该轮启动尚无引擎记录")


class FlowableNotSent(FlowableError):
    """连接建立前失败，可以重新发送同一条操作。"""


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

    def start_process(self, process_definition_id: str, business_key: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            "/flowable-rest/service/runtime/process-instances",
            json={"processDefinitionId": process_definition_id, "businessKey": business_key, "variables": _variables(variables or {})},
        )

    def definition_for_deployment(self, deployment_id: str, key: str) -> str:
        if not deployment_id:
            raise FlowableError(409, "该版本缺少部署记录")
        page = self._request("GET", "/flowable-rest/service/repository/process-definitions", params={"deploymentId": deployment_id, "key": key})
        definitions = page.get("data") or []
        if len(definitions) != 1 or page.get("total") != 1:
            raise FlowableError(409, "无法唯一确定该部署的流程版本")
        definition = definitions[0]
        if definition.get("key") != key or definition.get("deploymentId") != deployment_id or not definition.get("id"):
            raise FlowableError(409, "部署的流程版本不匹配")
        return str(definition["id"])

    def instance_for_business_key(self, business_key: str, definition_id: str) -> str:
        page = self._request(
            "GET",
            "/flowable-rest/service/history/historic-process-instances",
            params={"businessKey": business_key, "processDefinitionId": definition_id},
        )
        rows = page.get("data") or []
        if page.get("data") == [] and page.get("total") == 0:
            raise NoStartedInstance()
        if (
            len(rows) != 1
            or page.get("total") != 1
            or rows[0].get("businessKey") != business_key
            or rows[0].get("processDefinitionId") != definition_id
            or not rows[0].get("id")
        ):
            raise FlowableError(409, "流程启动结果待核对")
        return str(rows[0]["id"])

    def _all_runtime(self, resource, params):
        rows, seen = [], set()
        expected = None
        while True:
            page = self._request("GET", f"/flowable-rest/service/runtime/{resource}", params={**params, "start": len(rows), "size": 100})
            batch, total = page.get("data"), page.get("total")
            if not isinstance(batch, list) or type(total) is not int or page.get("start", len(rows)) != len(rows):
                raise FlowableError(502, "流程引擎分页响应不完整")
            if expected is not None and expected != total:
                raise FlowableError(409, "读取期间任务列表发生变化")
            expected = total
            ids = {row.get("id") for row in batch}
            if None in ids or len(ids) != len(batch) or ids & seen or len(rows) + len(batch) > total:
                raise FlowableError(409, "流程引擎分页结果不一致")
            rows.extend(batch)
            seen.update(ids)
            if len(rows) == total:
                return rows
            if not batch:
                raise FlowableError(502, "流程引擎分页提前结束")

    def active_activity_ids(self, process_instance_id: str) -> set[str]:
        executions = self._all_runtime("executions", {"processInstanceId": process_instance_id})
        return {
            row["activityId"]
            for row in executions
            if row.get("processInstanceId") == process_instance_id and row.get("activityId") and not row.get("suspended")
        }

    def list_tasks(self, process_instance_id: str) -> dict[str, Any]:
        rows = self._all_runtime("tasks", {"processInstanceId": process_instance_id})
        return {"data": rows, "total": len(rows)}

    def list_tasks_including_children(self, process_instance_id: str) -> list[dict[str, Any]]:
        pending, visited, tasks = [process_instance_id], set(), []
        while pending:
            instance_id = pending.pop()
            if instance_id in visited:
                continue
            visited.add(instance_id)
            tasks.extend({**row, "processInstanceId": instance_id} for row in self.list_tasks(instance_id)["data"])
            children = self._all_runtime("process-instances", {"superProcessInstanceId": instance_id})
            pending.extend(str(child["id"]) for child in children)
        return tasks

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

    def confirmed_external_job(self, process_id: str, name: str, value: str) -> bool:
        page = self._request(
            "GET",
            "/flowable-rest/service/history/historic-variable-instances",
            params={"processInstanceId": process_id, "variableName": name, "size": 2},
        )
        rows = page.get("data") or []
        if page.get("total") != 1 or len(rows) != 1:
            return False
        row = rows[0]
        variable = row.get("variable") or {}
        return (
            row.get("processInstanceId") == process_id
            and variable.get("name") == name
            and variable.get("scope") == "global"
            and variable.get("type") == "string"
            and variable.get("value") == value
        )

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

    def delete_process_instance(self, process_instance_id: str, *, reason: str = "") -> dict[str, Any]:
        return self._request(
            "DELETE", f"/flowable-rest/service/runtime/process-instances/{process_instance_id}", params={"deleteReason": reason} if reason else None
        )

    def confirmed_manual_action(self, op) -> bool:
        history = "/flowable-rest/service/history"
        if op.action in {"approve", "submit", "reject"}:
            name = "itsm_operation_receipt"
            rows = self._request(
                "GET",
                f"{history}/historic-variable-instances",
                params={
                    "processInstanceId": op.process_id,
                    "variableName": name,
                    "excludeTaskVariables": "true",
                },
            )
            return any(
                row.get("processInstanceId") == op.process_id
                and (row.get("variable") or {}).get("name") == name
                and row["variable"].get("value") == str(op.token)
                for row in rows.get("data", [])
            )
        if op.action in {"terminate", "withdraw", "close"}:
            row = self._request("GET", f"{history}/historic-process-instances/{op.process_id}")
            return bool(row.get("id") == op.process_id and row.get("endTime") and row.get("deleteReason") == str(op.token))
        if op.action in {"claim", "transfer"}:
            row = self._request("GET", f"/flowable-rest/service/runtime/tasks/{op.task_ref}")
            target = op.operator if op.action == "claim" else op.payload["data"]["target"]
            return row.get("id") == op.task_ref and row.get("processInstanceId") == op.process_id and row.get("assignee") == target
        if op.action == "return":
            old = self._request("GET", f"{history}/historic-task-instances/{op.task_ref}")
            target = op.payload["data"]["return_node_id"]
            return bool(
                old.get("id") == op.task_ref
                and old.get("processInstanceId") == op.process_id
                and old.get("endTime")
                and old.get("deleteReason") in {f"Change activity to {target}", f"Change parent activity to {target}"}
                and any(row.get("taskDefinitionKey") == target for row in self.list_tasks(op.process_id)["data"])
            )
        if op.action in {"suspend", "resume"}:
            row = self.get_process_instance(op.process_id)
            return row.get("id") == op.process_id and row.get("suspended") is (op.action == "suspend")
        return False

    def manual_action_unchanged(self, op) -> bool:
        if op.action in {"approve", "submit", "reject", "claim", "transfer", "return"}:
            row = self._request("GET", f"/flowable-rest/service/runtime/tasks/{op.task_ref}")
            if row.get("id") != op.task_ref or row.get("processInstanceId") != op.process_id:
                return False
            node_id = op.payload["node"].get("id") or (op.task.node_id if op.task_id else None)
            if not node_id or row.get("taskDefinitionKey") != node_id:
                return False
            if op.action in {"claim", "transfer"}:
                return "assignee" in row and (row["assignee"] or "") == op.payload.get("previous_assignee")
            return True
        row = self.get_process_instance(op.process_id)
        if row.get("id") != op.process_id or row.get("ended") is True:
            return False
        if op.action in {"suspend", "resume"}:
            return row.get("suspended") is (op.action == "resume")
        return op.action in {"terminate", "withdraw", "close"}

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
        reading = method.upper() in {"GET", "HEAD"}
        if not reading:
            kwargs["allow_redirects"] = False
        for _ in range(3 if reading else 1):
            try:
                response = self.session.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
            except requests.ConnectTimeout as exc:
                if not reading:
                    raise FlowableNotSent(0, "连接建立超时") from exc
                last_error = exc
                continue
            except requests.RequestException as exc:
                last_error = exc
                itsm_logger.warning("Flowable 请求失败: %s", type(exc).__name__)
                continue
            if response.status_code >= 500:
                last_error = FlowableError(response.status_code, response.text[:500])
                continue
            if 300 <= response.status_code < 400:
                raise FlowableError(502, "Flowable 返回了重定向")
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
