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
        self.port = int(params.get("port", 22))
        self.execute_timeout = int(params.get("execute_timeout", 60))
        self.node_info = params.get("node_info", {})
        self.model_id = params.get("model_id")

        if not self.script_path:
            raise ValueError("script_path is required for SSHPlugin")

    @property
    def namespace(self):
        """NATS 命名空间"""
        return os.getenv("NATS_NAMESPACE", "bklite")

    def _read_script(self) -> str:
        """读取脚本内容"""
        path = Path(self.script_path)

        if not path.exists():
            raise FileNotFoundError(f"Script not found: {self.script_path}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        logger.info(f"📖 Script loaded from {self.script_path}: {len(content)} bytes")
        return content

    def _build_exec_params(self, script_content: str) -> Dict[str, Any]:
        """构建执行参数"""
        exec_params = {
            "command": script_content,
            "port": self.port,
            "execute_timeout": self.execute_timeout
        }

        # 如果不是本地执行，需要 SSH 凭据
        if not self.node_info:
            exec_params.update({
                "host": self.host,
                "user": self.username,
                "username": self.username,
                "password": self.password
            })

        return exec_params

    async def list_all_resources(self) -> Dict[str, Any]:
        """
        执行脚本采集
        
        Returns:
            采集结果，格式：{"success": True, "result": "..."}
        """
        try:
            # 检查 Windows 系统
            if self.node_info and self.node_info.get("operating_system") == "windows":
                raise RuntimeError("当前节点为Windows系统，无法使用SSH方式采集数据")

            # 1. 读取脚本内容
            script_content = self._read_script()

            # 2. 构建执行参数
            exec_params = self._build_exec_params(script_content)

            # 3. 判断执行模式（本地 or SSH）
            execution_mode = "local" if self.node_info else "ssh"
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
                collect_data = response["result"]
                try:
                    # 尝试解析为 JSON
                    collect_data = json.loads(collect_data)
                except Exception:
                    collect_data = {}
                result = {"result": {self.model_id: [collect_data]}, "success": True}
            else:
                result = {"result": {"cmdb_collect_error": response.get("result")}, "success": False}
            logger.info(f"✅ Script execution completed: success={response.get('success')}")
            return result

        except Exception as e:
            import traceback
            logger.error(f"❌ SSHPlugin execution failed: {traceback.format_exc()}")
            return {"result": {"cmdb_collect_error": str(e)}, "success": False}
