# -*- coding: utf-8 -*-
"""
SSH 脚本执行器插件
用于统一处理所有基于脚本的采集任务
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.infra.nats_utils import nats_request
from core.logger import logger


class SSHPlugin:
    """
    SSH 脚本执行插件

    用于执行基于脚本的采集任务，支持：
    1. 自动判断本地执行还是 SSH 远程执行
    2. 从指定路径读取脚本
    3. 通过 NATS 执行脚本
    """

    def __init__(self, params: Dict[str, Any]):
        """
        初始化 SSH 插件

        Args:
            params: 参数字典，包含：
                - node_id: 节点 ID
                - host: 主机 IP
                - script_path: 脚本路径（必需）
                - username: SSH 用户名（可选）
                - password: SSH 密码（可选）
                - port: SSH 端口（默认 22）
                - execute_timeout: 超时时间（默认 60）
                - node_info: 节点信息（可选，用于判断本地执行）
        """
        # CMDB/监控侧偶发传 ansible_node_id；配置采集 header 为 cmdbnode_id→node_id
        self.node_id = str(params.get("node_id") or params.get("ansible_node_id") or "").strip()
        if not self.node_id:
            raise ValueError("node_id is required for SSHPlugin")
        self.host = params.get("host", "")
        self.connect_ip = params.get("connect_ip") or self.host
        script_path = params.get("script_path")
        self.username = params.get("username")
        self.password = params.get("password")
        self.private_key = params.get("private_key")
        self.passphrase = params.get("passphrase")
        # header 常把缺省 port 打成 ""；params.get("port", 22) 无法回落到默认值
        self.port = self._coerce_port(params.get("port"), default=22)
        # 脚本执行上限硬编码；表单 timeout 由框架作单对象采集预算，不写入此处。
        self.execute_timeout = 60
        self.probe_timeout = self._coerce_positive_float(params.get("timeout"), default=5.0)
        self.node_info = params.get("node_info", {})
        self.model_id = params.get("model_id")
        self.collection_task_id = params.get("collection_task_id") or params.get("task_id") or ""

        # NATS 请求超时 = 脚本执行超时 × 最大并发数
        # 原因：nats-executor 串行处理请求，排在队列后面的任务需要等待前面的任务完成
        # execute_timeout 仅控制单个脚本的执行时间，nats_timeout 需要覆盖排队等待时间
        max_jobs = int(os.getenv("TASK_MAX_JOBS", "10"))
        self.nats_timeout = self.execute_timeout * max_jobs

        if not script_path:
            raise ValueError("script_path is required for SSHPlugin")
        self.script_path = script_path

    @staticmethod
    def _coerce_port(raw, *, default: int = 22) -> int:
        if raw in (None, ""):
            return default
        port = int(raw)
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return port

    @staticmethod
    def _coerce_positive_int(raw, *, default: int) -> int:
        if raw in (None, ""):
            return default
        value = int(raw)
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value

    @staticmethod
    def _coerce_positive_float(raw, *, default: float) -> float:
        if raw in (None, ""):
            return default
        value = float(raw)
        if value <= 0:
            raise ValueError("timeout must be positive")
        return value

    @property
    def namespace(self):
        """NATS 命名空间"""
        return os.getenv("NATS_NAMESPACE", "bklite")

    def _get_shell_type(self) -> str:
        """
        根据脚本文件扩展名判断脚本类型

        Returns:
            脚本类型，支持: "sh"(默认), "bash", "bat", "cmd", "powershell", "pwsh"
        """
        path = Path(self.script_path)
        ext = path.suffix.lower()

        # 扩展名到 shell 类型的映射
        ext_to_shell = {
            ".sh": "bash",
            ".bash": "bash",
            ".bat": "bat",
            ".cmd": "cmd",
            ".ps1": "powershell",
            ".psm1": "powershell",
        }

        return ext_to_shell.get(ext, "sh")  # 默认返回 sh

    def _read_script(self) -> str:
        """读取脚本内容"""
        path = Path(self.script_path)

        # 如果是相对路径，转换为基于项目根目录的绝对路径
        if not path.is_absolute():
            # 获取当前文件所在目录的父目录的父目录（项目根目录）
            project_root = Path(__file__).parent.parent
            path = project_root / self.script_path

        if not path.exists():
            raise FileNotFoundError(f"Script not found: {path} (original: {self.script_path})")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        host_innerip = str(self.connect_ip or self.host or "").strip()
        if host_innerip:
            content = content.replace("{{bk_host_innerip}}", host_innerip)

        logger.debug(
            "event=ssh_script_loaded bytes=%s host=%s model_id=%s task_id=%s",
            len(content),
            self.host,
            self.model_id,
            self.collection_task_id,
        )
        return content

    def _build_exec_params(self, script_content: str) -> Dict[str, Any]:
        """构建执行参数"""
        exec_params = {
            "command": script_content,
            "execute_timeout": self.execute_timeout,
        }

        # 如果不是本地执行，需要 SSH 凭据
        if not self.node_info:
            exec_params.update(
                {
                    "host": self.connect_ip,
                    "user": self.username,
                    "username": self.username,
                    "password": self.password,
                    "port": self.port,
                    "connection_test": True,
                }
            )
            # 私钥认证（可选）：与密码路径互斥由上层任务参数保证
            if self.private_key:
                exec_params["private_key"] = self.private_key
            if self.passphrase:
                exec_params["passphrase"] = self.passphrase
        else:
            # 本地执行时指定脚本类型
            shell_type = self._get_shell_type()
            exec_params["shell"] = shell_type
            logger.debug(
                "event=ssh_local_execution shell=%s host=%s model_id=%s task_id=%s",
                shell_type,
                self.host,
                self.model_id,
                self.collection_task_id,
            )

        return exec_params

    def _parse_collect_output(self, collect_output: str) -> List[Dict[str, Any]]:
        if not collect_output:
            return []
        try:
            parsed = json.loads(collect_output)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                return [parsed]
        except Exception:
            pass
        records: List[Dict[str, Any]] = []
        for line in collect_output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed_line = json.loads(stripped)
                if isinstance(parsed_line, dict):
                    records.append(parsed_line)
            except Exception:
                continue
        return records

    async def probe(self) -> AccessProbeResult:
        if self.node_info:
            return AccessProbeResult(status=AccessProbeStatus.READY)
        exec_params = self._build_exec_params("true")
        subject = f"ssh.execute.{self.node_id}"
        payload = json.dumps({"args": [exec_params], "kwargs": {}}).encode()
        try:
            response = await nats_request(
                subject,
                payload=payload,
                timeout=self.probe_timeout,
            )
        except TimeoutError:
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_probe_no_response",
            )
        if response.get("success"):
            return AccessProbeResult(status=AccessProbeStatus.READY)
        error = str(response.get("error") or response.get("result") or "").lower()
        if any(
            marker in error
            for marker in (
                "permission denied",
                "authentication failed",
                "unauthorized",
            )
        ):
            return AccessProbeResult(
                status=AccessProbeStatus.AUTH_FAILED,
                error_code="authentication_failed",
            )
        if any(marker in error for marker in ("no route", "connection refused", "host is down")):
            return AccessProbeResult(
                status=AccessProbeStatus.TARGET_UNREACHABLE,
                error_code="target_unreachable",
            )
        if "timed out" in error or "timeout" in error:
            return AccessProbeResult(
                status=AccessProbeStatus.NO_RESPONSE,
                error_code="protocol_probe_no_response",
            )
        return AccessProbeResult(
            status=AccessProbeStatus.SERVICE_UNAVAILABLE,
            error_code="remote_probe_failed",
        )

    async def list_all_resources(self, need_raw=False) -> Dict[str, Any]:
        """
        执行脚本采集

        Returns:
            采集结果，格式：{"success": True, "result": "..."}
            need_raw： 是否需要原始结果
        """
        try:
            # 1. 读取脚本内容
            script_content = await asyncio.to_thread(self._read_script)

            # 2. 构建执行参数
            exec_params = self._build_exec_params(script_content)
            # 3. 判断执行模式（本地 or SSH）
            execution_mode = "local" if self.node_info else "ssh"
            # 如果是local，则使用对应的node_id
            if execution_mode == "local":
                subject = f"{execution_mode}.execute.{self.node_info['id']}"
            else:
                subject = f"{execution_mode}.execute.{self.node_id}"

            logger.debug(
                "event=ssh_script_execute mode=%s host=%s model_id=%s task_id=%s",
                execution_mode,
                self.host,
                self.model_id,
                self.collection_task_id,
            )

            # 4. 通过 NATS 执行
            payload = json.dumps({"args": [exec_params], "kwargs": {}}).encode()
            response = await nats_request(subject, payload=payload, timeout=self.nats_timeout)
            if response.get("success"):
                if need_raw:
                    return response
                collect_data = response["result"]
                parsed_payload = self._parse_collect_output(collect_data)
                if parsed_payload:
                    result = {
                        "result": {self.model_id: parsed_payload},
                        "success": True,
                    }
                else:
                    result = {"result": {}, "success": True}
                logger.info(
                    "event=ssh_script_completed success=%s host=%s model_id=%s task_id=%s",
                    True,
                    self.host,
                    self.model_id,
                    self.collection_task_id,
                )
            else:
                # nats-executor 的错误信息在 "error" 字段，"result" 字段是命令输出（探测失败时为空）
                error_msg = response.get("error") or response.get("result") or "Unknown error"
                result = {
                    "result": {"cmdb_collect_error": error_msg},
                    "success": False,
                }
                logger.warning(
                    "event=ssh_script_completed success=%s host=%s model_id=%s task_id=%s failed_stage=%s",
                    False,
                    self.host,
                    self.model_id,
                    self.collection_task_id,
                    "nats_execute",
                )
            return result
        except Exception as e:
            logger.exception(
                "event=ssh_script_failed host=%s model_id=%s task_id=%s failed_stage=%s error_type=%s",
                self.host,
                self.model_id,
                self.collection_task_id,
                "ssh_script_execute",
                type(e).__name__,
            )
            return {"result": {"cmdb_collect_error": str(e)}, "success": False}


# if __name__ == '__main__':
#     import os
#     os.environ["NATS_URLS"] = ""
#     os.environ["NATS_TLS_ENABLED"] = "true"
#     os.environ["NATS_TLS_CA_FILE"] = ""
#     params = {
#         "node_id": "",
#         "host": "172.30.112.1",
#         "script_path": "plugins/inputs/host/host_windows_discover.ps1",
#         "model_id": "host",
#         "node_info": {"name": 1}
#     }
#     plugin = SSHPlugin(params=params)
#     import asyncio
#
#     asyncio.run(plugin.list_all_resources())
