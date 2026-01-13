# -*- coding: utf-8 -*-
"""
SSH 脚本执行器插件
用于统一处理所有基于脚本的采集任务
"""
import os
import json
from pathlib import Path
from typing import Dict, Any
from sanic.log import logger
from core.nats_utils import nats_request


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
        self.node_id = params["node_id"]
        self.host = params.get("host", "")
        self.script_path = params.get("script_path")
        self.username = params.get("username")
        self.password = params.get("password")
        self.port = params.get("port", 22)
        self.execute_timeout = int(params.get("execute_timeout", 60))
        self.node_info = params.get("node_info", {})
        self.model_id = params.get("model_id")

        if not self.script_path:
            raise ValueError("script_path is required for SSHPlugin")

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
            '.sh': 'bash',
            '.bash': 'bash',
            '.bat': 'bat',
            '.cmd': 'cmd',
            '.ps1': 'powershell',
            '.psm1': 'powershell',
        }

        return ext_to_shell.get(ext, 'sh')  # 默认返回 sh

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

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        logger.info(f"📖 Script loaded from {path}: {len(content)} bytes")
        return content

    def _build_exec_params(self, script_content: str) -> Dict[str, Any]:
        """构建执行参数"""
        exec_params = {
            "command": script_content,
            "execute_timeout": self.execute_timeout
        }

        # 如果不是本地执行，需要 SSH 凭据
        if not self.node_info:
            exec_params.update({
                "host": self.host,
                "user": self.username,
                "username": self.username,
                "password": self.password,
                "port": int(self.port)
            })
        else:
            # 本地执行时指定脚本类型
            shell_type = self._get_shell_type()
            exec_params["shell"] = shell_type
            logger.info(f"🔧 Local execution: shell type={shell_type}")

        return exec_params

    async def list_all_resources(self, need_raw=False) -> Dict[str, Any]:
        """
        执行脚本采集
        
        Returns:
            采集结果，格式：{"success": True, "result": "..."}
            need_raw： 是否需要原始结果
        """
        try:
            # 1. 读取脚本内容
            script_content = self._read_script()

            # 2. 构建执行参数
            exec_params = self._build_exec_params(script_content)
            # 3. 判断执行模式（本地 or SSH）
            execution_mode = "local" if self.node_info else "ssh"
            # 如果是local，则使用对应的node_id
            if execution_mode == "local":
                subject = f"{execution_mode}.execute.{self.node_info['id']}"
            else:
                subject = f"{execution_mode}.execute.{self.node_id}"

            logger.info(f"🚀 Executing script via NATS: mode={execution_mode}, subject={subject}")

            # 4. 通过 NATS 执行
            payload = json.dumps({"args": [exec_params], "kwargs": {}}).encode()
            response = await nats_request(
                subject,
                payload=payload,
                timeout=self.execute_timeout
            )
            if response.get("success"):
                if need_raw:
                    return response
                collect_text = response.get("result", "")
                parsed_items = self._parse_collect_output(collect_text)
                result = {"result": {self.model_id: parsed_items}, "success": True}
            else:
                result = {"result": {"cmdb_collect_error": response.get("result")}, "success": False}
            logger.info(f"✅ Script execution completed: success={response.get('success')}")
            return result
        except Exception as e:
            import traceback
            logger.error(f"❌ SSHPlugin execution failed: {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(e)}, "success": False}

    @staticmethod
    def _parse_collect_output(collect_text: str):
        """解析脚本 stdout。

        兼容以下输出形式：
        - 单个 JSON 对象（推荐）：{"a":1}
        - JSON 数组：[{"a":1},{"b":2}]
        - 多行 JSON（每行一个对象）：\n 分隔

        为保持兼容：
        - 当完全无法解析出任何 JSON 时，返回 [{}]（与旧逻辑 json.loads 失败回退为 {} 基本一致）。
        """
        text = (collect_text or "").strip()
        if not text:
            return [{}]

        # 1) 优先尝试整体按 JSON 解析
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return [obj]
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)] or [{}]
        except Exception:
            pass

        # 1.5) stdout 可能混入提示/告警/日志，尝试从文本中提取 JSON 片段（支持多段 JSON）
        decoder = json.JSONDecoder()
        extracted: list[dict] = []

        idx = 0
        while idx < len(text):
            next_obj = text.find("{", idx)
            next_arr = text.find("[", idx)
            if next_obj == -1 and next_arr == -1:
                break

            # 选择更靠前的起点
            if next_obj == -1:
                start = next_arr
            elif next_arr == -1:
                start = next_obj
            else:
                start = min(next_obj, next_arr)

            try:
                obj, end = decoder.raw_decode(text, start)
                if isinstance(obj, dict):
                    extracted.append(obj)
                elif isinstance(obj, list):
                    extracted.extend([x for x in obj if isinstance(x, dict)])
                idx = end
            except Exception:
                idx = start + 1

        if extracted:
            return extracted

        # 2) 再尝试逐行解析（脚本可能输出多行，每行一个 JSON）
        parsed = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    parsed.append(obj)
                elif isinstance(obj, list):
                    parsed.extend([x for x in obj if isinstance(x, dict)])
            except Exception:
                continue

        return parsed or [{}]


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
