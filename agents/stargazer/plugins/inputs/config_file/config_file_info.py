# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import ntpath
import posixpath
from typing import Any, Dict
import time

from sanic.log import logger

from plugins.script_executor import SSHPlugin


class ConfigFileInfo(SSHPlugin):
    def __init__(self, params: Dict[str, Any]):
        self.params = params
        super().__init__(params)

    async def list_all_resources(self, need_raw=False) -> Dict[str, Any]:
        try:
            config_file_path = self._get_config_file_path()
            script_content = self._read_script()
            rendered_script = self._render_script(script_content, config_file_path)
            response = await self._execute_script(rendered_script)
            if need_raw:
                return response

            if not response.get("success"):
                error_msg = response.get("error") or response.get("result") or "Unknown error"
                return {
                    "result": {"cmdb_collect_error": error_msg},
                    "success": False,
                }

            payload = self._parse_collect_output(response.get("result", ""))
            return {"success": True, "result": self._build_callback_payload(payload)}
        except Exception as err:
            import traceback

            logger.error(
                f"{self.__class__.__name__} main error! {traceback.format_exc()}"
            )
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}

    def _render_script(self, script_content: str, config_file_path: str) -> str:
        replacements = {
            "{{config_file_path}}": self._escape_script_value(config_file_path),
        }
        rendered = script_content
        for source, target in replacements.items():
            rendered = rendered.replace(source, target)
        return rendered

    async def _execute_script(self, script_content: str) -> Dict[str, Any]:
        exec_params = self._build_exec_params(script_content)
        execution_mode = "local" if self.node_info else "ssh"
        if execution_mode == "local":
            subject = f"{execution_mode}.execute.{self.node_info['id']}"
        else:
            subject = f"{execution_mode}.execute.{self.node_id}"

        payload = json.dumps({"args": [exec_params], "kwargs": {}}).encode()
        from core.nats_utils import nats_request

        return await nats_request(
            subject, payload=payload, timeout=self.nats_timeout
        )

    def _get_config_file_path(self) -> str:
        """配置文件插件直接消费完整文件绝对路径。"""
        file_path = str(self.params.get("config_file_path") or "").strip()
        if not file_path:
            raise ValueError("config_file_path is required")
        return file_path

    @staticmethod
    def _extract_file_name(file_path: str) -> str:
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return ""
        if ":\\" in normalized_path or "\\" in normalized_path:
            return ntpath.basename(normalized_path)
        return posixpath.basename(normalized_path)

    def _build_callback_payload(self, payload: dict) -> dict:
        status = str(payload.get("status") or "error").lower()
        content_base64 = payload.get("content_base64", "")
        content_hash = ""
        if status == "success" and content_base64:
            try:
                raw_content = base64.b64decode(content_base64)
                content_hash = hashlib.sha256(raw_content).hexdigest()
            except Exception:
                status = "error"
                payload["error"] = "配置文件内容解码失败"
                payload["error_type"] = "error"
                content_base64 = ""

        instance_name = str(self.params.get("host") or self.params.get("instance_name") or "")
        model_id = (
            self.params.get("target_model_id")
            or self.params.get("model_id")
            or "host"
        )
        version = str(int(time.time() * 1000))
        return {
            "collect_task_id": self.params.get("collect_task_id"),
            "execution_id": self.params.get("execution_id"),
            "instance_id": instance_name,
            "instance_name": instance_name,
            "model_id": model_id,
            "file_path": self._get_config_file_path(),
            "file_name": self._extract_file_name(self._get_config_file_path()),
            "version": version,
            "status": payload.get("error_type") if status != "success" else "success",
            "size": payload.get("size", 0),
            "error": payload.get("error", ""),
            "content_base64": content_base64,
            "content_hash": content_hash,
        }

    def _parse_collect_output(self, collect_output: str) -> dict:
        if not collect_output:
            return {
                "status": "error",
                "error_type": "error",
                "error": "空采集结果",
                "size": 0,
            }
        lines = [line.strip() for line in collect_output.splitlines() if line.strip()]
        last_line = lines[-1] if lines else ""
        try:
            parsed = json.loads(last_line)
        except Exception as err:
            return {
                "status": "error",
                "error_type": "error",
                "error": f"结果解析失败: {err}",
                "size": 0,
            }
        return (
            parsed
            if isinstance(parsed, dict)
            else {
                "status": "error",
                "error_type": "error",
                "error": "结果格式错误",
                "size": 0,
            }
        )

    @staticmethod
    def _escape_script_value(value: str) -> str:
        return str(value or "").replace("'", "'\"'\"'")
