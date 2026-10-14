# -*- coding: utf-8 -*-
"""自定义脚本采集：脚本由 Run 准备期注入，Linux 走 SSHPlugin，Windows 走 WinRM。"""

import json
import os
import re

from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.infra.ansible_rpc import ansible_adhoc
from plugins.script_executor import SSHPlugin

MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 5000
MAX_FIELD_LENGTH = 1024
_CREDENTIAL_PLACEHOLDER = re.compile(r"\{\{credential\.([a-z][a-z0-9_]{0,31})\}\}")
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)


class ScriptFetchError(RuntimeError):
    pass


def render_script(content, params):
    rendered = str(content or "")
    values = {}
    for key, value in (params or {}).items():
        if key.startswith("credential_") or key in {"password", "private_key", "passphrase"}:
            continue
        if isinstance(value, (str, int, float)):
            values[key] = str(value)

    def _replace(match):
        return values.get(match.group(1), "")

    return _CREDENTIAL_PLACEHOLDER.sub(_replace, rendered)


def parse_records(stdout):
    text = str(stdout or "").strip()
    if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        text = text.encode("utf-8")[:MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore")
    records = []
    try:
        parsed = json.loads(text)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except (TypeError, ValueError):
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not str(row.get("inst_name") or "").strip():
            continue
        limited = {}
        for key, value in row.items():
            if isinstance(value, str) and len(value) > MAX_FIELD_LENGTH:
                value = value[:MAX_FIELD_LENGTH]
            if isinstance(value, (list, dict)):
                continue
            limited[key] = value
        records.append(limited)
        if len(records) >= MAX_RECORDS:
            break
    return records


def scrub_secrets(text, params):
    masked = _PRIVATE_KEY_BLOCK_RE.sub("***", str(text or ""))
    for key, value in (params or {}).items():
        if not isinstance(value, str) or len(value) < 4:
            continue
        if key in {"password", "private_key", "passphrase"} or key.endswith("password") or key.endswith("token"):
            masked = masked.replace(value, "***")
    return masked


class CustomScriptCollector:
    def __init__(self, params):
        self.params = params or {}
        self.plugin_id = str(self.params.get("custom_plugin_id") or "")
        self.os_type = str(self.params.get("os_type") or "")
        timeout = self.params.get("timeout") or 60
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = 60
        self.execute_timeout = max(1, min(timeout, 600))

    async def probe(self):
        if self.os_type == "windows":
            return AccessProbeResult(status=AccessProbeStatus.NOT_SUPPORTED)
        plugin = SSHPlugin(self._linux_params("true"))
        return await plugin.probe()

    async def list_all_resources(self, need_raw=False):
        content = self.params.get("script_content")
        if not content or not self.plugin_id:
            return {"success": False, "result": {"cmdb_collect_error": "SCRIPT_FETCH_FAILED"}}
        rendered = render_script(content, self.params)
        try:
            if self.os_type == "windows":
                stdout = await self._run_windows(rendered)
            else:
                stdout = await self._run_linux(rendered)
        except Exception as exc:  # noqa: BLE001 - 执行失败收敛为稳定错误码
            return {"success": False, "result": {"cmdb_collect_error": scrub_secrets(exc, self.params)}}
        records = parse_records(stdout)
        return {"success": True, "result": {self.plugin_id: records}}

    def _linux_params(self, script_content):
        params = dict(self.params)
        params["script_content"] = script_content
        params["execute_timeout"] = self.execute_timeout
        params.pop("script_path", None)
        return params

    async def _run_linux(self, rendered):
        plugin = SSHPlugin(self._linux_params(rendered))
        raw = await plugin.list_all_resources(need_raw=True)
        if not raw.get("success"):
            error_text = (raw.get("result") or {}).get("cmdb_collect_error", "")
            raise RuntimeError(error_text or "SCRIPT_OUTPUT_INVALID")
        return raw.get("result") or ""

    async def _run_windows(self, rendered):
        credential = {
            "host": self.params.get("host") or self.params.get("connect_ip"),
            "user": self.params.get("username", ""),
            "connection": "winrm",
            "port": int(self.params.get("port") or 5986),
            "password": self.params.get("password", ""),
            "winrm_scheme": self.params.get("winrm_scheme") or "https",
            "winrm_transport": self.params.get("winrm_transport") or "ntlm",
            "winrm_cert_validation": str(self.params.get("winrm_cert_validation") or "").lower() in {"1", "true", "yes"},
        }
        shell = str(self.params.get("shell") or "powershell").strip().lower()
        script_type = "bat" if shell == "bat" else "powershell"
        result = await ansible_adhoc(
            ansible_node_id=self.params.get("ansible_node_id") or self.params.get("node_id"),
            host_credentials=[credential],
            module="win_shell",
            module_args=rendered,
            execute_timeout=self.execute_timeout,
            stream_remote_type=script_type,
        )
        if not result.get("success"):
            raise RuntimeError("TARGET_UNREACHABLE")
        return _windows_stdout(result.get("result"), credential["host"])


def _windows_stdout(task_result, host):
    """Ansible adhoc 的 result 可能是主机列表，也可能是 host 到结果的字典。"""

    if isinstance(task_result, str):
        return task_result
    host_data = _first_windows_host_data(task_result, host)
    if not isinstance(host_data, dict):
        return ""
    return str(host_data.get("stdout") or "")


def _first_windows_host_data(task_result, host):
    expected_host = str(host or "")
    if isinstance(task_result, list):
        for item in task_result:
            if isinstance(item, dict) and str(item.get("host") or "") == expected_host:
                return item
        for item in task_result:
            if isinstance(item, dict):
                return item
        return None
    if not isinstance(task_result, dict):
        return None
    if "stdout" in task_result or "rc" in task_result:
        return task_result
    hosts_result = task_result.get("contacted", task_result)
    if not isinstance(hosts_result, dict):
        return None
    matched = hosts_result.get(expected_host)
    if isinstance(matched, dict):
        return matched
    for item in hosts_result.values():
        if isinstance(item, dict):
            return item
    return None


async def fetch_custom_script(collect_task_id):
    from core.infra.nats_utils import nats_request

    namespace = os.getenv("NATS_NAMESPACE", "bklite")
    payload = json.dumps({"args": [{"collect_task_id": collect_task_id}], "kwargs": {}}).encode()
    response = await nats_request(f"{namespace}.cmdb_get_custom_script", payload=payload, timeout=15)
    if not isinstance(response, dict) or not response.get("success"):
        raise ScriptFetchError("SCRIPT_FETCH_FAILED")
    result = response.get("result") or {}
    if not result.get("content"):
        raise ScriptFetchError("SCRIPT_FETCH_FAILED")
    return result
