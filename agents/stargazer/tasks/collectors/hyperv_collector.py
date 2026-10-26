# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path
from typing import Any, Dict
from urllib.parse import unquote

from core.infra.ansible_rpc import ansible_adhoc

from .base_collector import BaseCollector
from .host_collector import (
    ANSIBLE_ADHOC_FAILED_LOG_TEMPLATE,
    _as_bool,
    classify_ansible_failure,
    extract_ansible_failure_summary,
    format_ansible_failure_message,
)
from .hyperv_metrics import parse_hyperv_metrics_to_prometheus

logger = logging.getLogger("stargazer.hyperv_collector")
SCRIPT_PATH = Path(__file__).parent / "scripts" / "windows" / "hyperv.ps1"


def _url_decode_secret(value: Any, credential_encoding: Any = "url") -> str:
    if not value:
        return value
    if str(credential_encoding or "url").strip().lower() in {"plain", "raw", "none"}:
        return str(value)
    return unquote(str(value))


class HypervCollector(BaseCollector):
    def _script(self) -> str:
        return SCRIPT_PATH.read_text(encoding="utf-8")

    def _resolve_execution_config(self) -> Dict[str, Any]:
        host = self.params["host"]
        raw_port = self.params.get("port")
        port = int(raw_port) if raw_port not in (None, "") else 5985
        ansible_node_id = self.params.get("ansible_node_id") or self.params.get("node_id")
        if not ansible_node_id:
            raise ValueError("ansible_node_id is required for Hyper-V collection")
        encoding = self.params.get("credential_encoding") or self.params.get("credentials_encoding") or "url"
        return {
            "host": host,
            "ansible_node_id": ansible_node_id,
            "module": "win_shell",
            "module_args": self._script(),
            "execute_timeout": int(self.params.get("timeout") or 60),
            "host_credentials": [
                {
                    "host": host,
                    "user": self.params["username"],
                    "password": _url_decode_secret(self.params.get("password", ""), encoding),
                    "connection": "winrm",
                    "port": port,
                    "winrm_scheme": self.params.get("winrm_scheme") or "http",
                    "winrm_transport": self.params.get("winrm_transport") or "ntlm",
                    "winrm_cert_validation": _as_bool(self.params.get("winrm_cert_validation"), default=False),
                }
            ],
        }

    async def collect(self) -> str:
        logger.info("event=hyperv_collect_start host=%s", self.params.get("host"))
        config = self._resolve_execution_config()
        result = await ansible_adhoc(
            ansible_node_id=config["ansible_node_id"],
            host_credentials=config["host_credentials"],
            module=config["module"],
            module_args=config["module_args"],
            execute_timeout=config["execute_timeout"],
        )
        return self.process_adhoc_result(result)

    async def submit_collection(self, task_id: str, callback_subject: str, callback_payload: Dict[str, Any]) -> Dict[str, Any]:
        config = self._resolve_execution_config()
        callback = dict(callback_payload or {})
        callback.update({"subject": callback_subject, "timeout": int(self.params.get("timeout") or 60)})
        return await ansible_adhoc(
            ansible_node_id=config["ansible_node_id"],
            host_credentials=config["host_credentials"],
            module=config["module"],
            module_args=config["module_args"],
            execute_timeout=config["execute_timeout"],
            callback=callback,
            task_id=task_id,
        )

    def process_adhoc_result(self, result: Dict[str, Any]) -> str:
        host = self.params["host"]
        if not result.get("success"):
            summary = extract_ansible_failure_summary(result, host)
            logger.error(
                ANSIBLE_ADHOC_FAILED_LOG_TEMPLATE,
                host,
                summary["error"],
                summary["host_status"] or "-",
                summary["exit_code"] or "-",
                summary["stderr"] or "-",
                summary["stderr_missing"],
                classify_ansible_failure(summary),
            )
            raise RuntimeError(format_ansible_failure_message(summary))
        stdout = self._extract_stdout(result)
        if not stdout or not stdout.strip():
            raise RuntimeError(f"Hyper-V collection returned empty stdout for {host}")
        try:
            payload = json.loads(stdout.strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Hyper-V collection returned invalid JSON for {host}: {exc}") from exc
        tags = dict(self.params.get("tags") or {})
        tags.setdefault("host", host)
        tags.setdefault("instance_id", self.params.get("instance_id") or host)
        tags.setdefault("instance_type", "hyperv")
        tags.setdefault("collect_type", "http")
        tags.setdefault("config_type", "hyperv")
        return parse_hyperv_metrics_to_prometheus(payload, tags)

    def _extract_stdout(self, result: Dict[str, Any]) -> str:
        task_result = result.get("result", {})
        if isinstance(task_result, str):
            return task_result
        expected = str(self.params.get("host") or "")
        if isinstance(task_result, list):
            for item in task_result:
                if isinstance(item, dict) and str(item.get("host") or "") == expected:
                    return str(item.get("stdout") or "")
            for item in task_result:
                if isinstance(item, dict) and item.get("stdout"):
                    return str(item.get("stdout") or "")
            return ""
        if isinstance(task_result, dict):
            hosts_result = task_result.get("contacted", task_result)
            if expected in hosts_result and isinstance(hosts_result[expected], dict):
                return str(hosts_result[expected].get("stdout") or "")
            for value in hosts_result.values():
                if isinstance(value, dict) and value.get("stdout"):
                    return str(value.get("stdout") or "")
        return ""
