"""受限 Pod exec：白名单诊断命令，禁止 shell 与路径穿透。"""

import json
import re

from kubernetes import client
from kubernetes.client import ApiException
from kubernetes.stream import stream
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.tools.kubernetes.utils import prepare_context

_ALLOWED_EXEC_BINARIES = frozenset({"curl", "nslookup", "dig", "env", "hostname", "date", "wget", "ping", "ss", "ip"})
_UNSAFE_TOKEN_RE = re.compile(r"[;&|`$<>\n\r]")
_MIN_EXEC_TIMEOUT = 1
_MAX_EXEC_TIMEOUT = 30
_DEFAULT_EXEC_TIMEOUT = 10


def _normalize_exec_command(command):
    if isinstance(command, str):
        return None, 'command 必须是字符串数组，例如 ["curl", "-s", "http://127.0.0.1:8848/ready"]'
    if not isinstance(command, (list, tuple)) or not command:
        return None, "command 必须是非空字符串数组"
    parts = [str(item) for item in command]
    if any(_UNSAFE_TOKEN_RE.search(part) for part in parts):
        return None, "command 含有不允许的 shell 元字符"
    binary = parts[0]
    if "/" in binary or "\\" in binary:
        return None, "只允许无路径的白名单命令"
    if binary not in _ALLOWED_EXEC_BINARIES:
        return None, f"命令不在白名单: {binary}。允许: {', '.join(sorted(_ALLOWED_EXEC_BINARIES))}"
    return parts, None


def _clamp_timeout(timeout) -> int:
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        value = _DEFAULT_EXEC_TIMEOUT
    return max(_MIN_EXEC_TIMEOUT, min(_MAX_EXEC_TIMEOUT, value))


@tool()
def exec_in_pod(
    namespace,
    pod_name,
    command,
    container=None,
    timeout=None,
    config: RunnableConfig = None,
):
    """
    在 Pod 内容器中执行白名单诊断命令（无 shell、无 stdin/tty）。

    允许的二进制：curl、nslookup、dig、env、hostname、date、wget、ping、ss、ip。
    command 必须是参数数组，禁止 sh/bash 与 ;|& 等元字符。
    本工具带 approval.required，审批开启时会进入人工确认。
    """
    parts, error = _normalize_exec_command(command)
    if error:
        return json.dumps({"success": False, "error": error}, ensure_ascii=False)
    if not namespace or not pod_name:
        return json.dumps({"success": False, "error": "需要指定 namespace 和 pod_name"}, ensure_ascii=False)

    prepare_context(config)
    timeout_seconds = _clamp_timeout(timeout if timeout is not None else _DEFAULT_EXEC_TIMEOUT)
    try:
        core_v1 = client.CoreV1Api()
        kwargs = {
            "command": parts,
            "stderr": True,
            "stdin": False,
            "stdout": True,
            "tty": False,
            "_request_timeout": timeout_seconds,
        }
        if container:
            kwargs["container"] = container
        logger.info("exec_in_pod started namespace=%s pod=%s binary=%s", namespace, pod_name, parts[0])
        output = stream(core_v1.connect_get_namespaced_pod_exec, pod_name, namespace, **kwargs)
        stdout = output if isinstance(output, str) else str(output or "")
        return json.dumps(
            {
                "success": True,
                "namespace": namespace,
                "pod_name": pod_name,
                "command": parts,
                "stdout": stdout,
            },
            ensure_ascii=False,
        )
    except ApiException as exc:
        logger.error(
            "exec_in_pod failed namespace=%s pod=%s failed_stage=exec error_type=%s",
            namespace,
            pod_name,
            type(exc).__name__,
        )
        return json.dumps({"success": False, "error": f"exec 失败: {exc}"}, ensure_ascii=False)
    except Exception as exc:
        logger.error(
            "exec_in_pod failed namespace=%s pod=%s failed_stage=exec error_type=%s",
            namespace,
            pod_name,
            type(exc).__name__,
        )
        return json.dumps({"success": False, "error": f"exec 失败: {exc}"}, ensure_ascii=False)


if exec_in_pod.metadata is None:
    exec_in_pod.metadata = {}
exec_in_pod.metadata["approval"] = {
    "required": True,
    "description": "在 Pod 内执行白名单诊断命令，需人工审批",
}
