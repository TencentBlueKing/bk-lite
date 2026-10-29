# -*- coding: utf-8 -*-
import json
from typing import Any, Dict

from core.infra.ansible_rpc import ansible_adhoc
from core.logger import logger
from tasks.collectors.hyperv_metrics import cmdb_payload_from_discover


class HypervInfo:
    def __init__(self, params: Dict[str, Any]):
        self.params = params or {}
        self.host = self.params.get("host") or self.params.get("connect_ip") or ""
        self.node_id = str(self.params.get("node_id") or self.params.get("ansible_node_id") or "").strip()
        if not self.node_id:
            raise ValueError("node_id is required for HypervInfo")
        self.username = self.params.get("username")
        self.password = self.params.get("password")
        raw_port = self.params.get("port")
        self.port = int(raw_port) if raw_port not in (None, "") else 5985
        self.execute_timeout = int(self.params.get("execute_timeout") or self.params.get("timeout") or 60)
        self.model_id = self.params.get("model_id") or "hyperv_host"
        self.collection_task_id = self.params.get("collection_task_id") or self.params.get("task_id") or ""
        self.script_path = self.params.get("script_path") or "plugins/inputs/hyperv_host/hyperv_discover.ps1"

    def _read_script(self) -> str:
        from pathlib import Path

        path = Path(self.script_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / self.script_path
        content = path.read_text(encoding="utf-8")
        if self.host:
            content = content.replace("{{bk_host_innerip}}", str(self.host))
        return content

    async def list_all_resources(self, need_raw=False) -> Dict[str, Any]:
        try:
            script = self._read_script()
            result = await ansible_adhoc(
                ansible_node_id=self.node_id,
                host_credentials=[
                    {
                        "host": self.host,
                        "user": self.username,
                        "password": self.password,
                        "connection": "winrm",
                        "port": self.port,
                        "winrm_scheme": self.params.get("winrm_scheme") or "http",
                        "winrm_transport": self.params.get("winrm_transport") or "ntlm",
                        "winrm_cert_validation": str(self.params.get("winrm_cert_validation") or "").lower() in {"1", "true", "yes"},
                    }
                ],
                module="win_shell",
                module_args=script,
                execute_timeout=self.execute_timeout,
            )
            if not result.get("success"):
                error = result.get("error") or result.get("result") or "Hyper-V WinRM collect failed"
                return {"success": False, "result": {"cmdb_collect_error": str(error)}}
            stdout = _stdout(result.get("result"), self.host)
            payload = json.loads(stdout.strip()) if stdout and stdout.strip() else {}
            mapped = cmdb_payload_from_discover(payload, host_ip=self.host)
            logger.info(
                "event=hyperv_collect_completed host=%s task_id=%s host_count=%s vm_count=%s",
                self.host,
                self.collection_task_id,
                len(mapped.get("hyperv_host") or []),
                len(mapped.get("hyperv_vm") or []),
            )
            if need_raw:
                return {"success": True, "result": stdout}
            return {"success": True, "result": mapped}
        except Exception as err:
            logger.exception(
                "event=hyperv_collect_failed host=%s task_id=%s error_type=%s",
                self.host,
                self.collection_task_id,
                type(err).__name__,
            )
            return {"success": False, "result": {"cmdb_collect_error": str(err)}}


def _stdout(task_result, host: str) -> str:
    if isinstance(task_result, str):
        return task_result
    expected = str(host or "")
    if isinstance(task_result, list):
        for item in task_result:
            if isinstance(item, dict) and str(item.get("host") or "") == expected:
                return str(item.get("stdout") or "")
        for item in task_result:
            if isinstance(item, dict) and item.get("stdout"):
                return str(item.get("stdout") or "")
        return ""
    if isinstance(task_result, dict):
        contacted = task_result.get("contacted", task_result)
        if expected in contacted and isinstance(contacted[expected], dict):
            return str(contacted[expected].get("stdout") or "")
        for value in contacted.values():
            if isinstance(value, dict) and value.get("stdout"):
                return str(value.get("stdout") or "")
    return ""
