"""
动作节点（HTTP请求、定时任务等）
"""

import base64
import json
from typing import Any, Dict

import requests
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.safe_requests import safe_delete, safe_get, safe_patch, safe_post, safe_put
from apps.core.utils.safe_template import TemplateSecurityError, safe_render
from apps.opspilot.models import WorkflowAttachmentAsset
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.rpc.system_mgmt import SystemMgmt


class HttpActionNode(BaseNodeExecutor):
    """支持模板变量的HTTP请求节点"""

    def _render_template(self, content: str, node_id: str, template_context: Dict[str, Any]) -> str:
        """使用安全模板渲染

        Args:
            content: 待渲染内容
            node_id: 节点ID
            template_context: 模板上下文变量

        Returns:
            渲染后的内容
        """
        if not content:
            return content

        try:
            return safe_render(str(content), template_context)
        except TemplateSecurityError as e:
            logger.error(f"HTTP节点 {node_id} 模板安全校验失败: {e}")
            raise ValueError(f"模板包含不安全内容: {e}")
        except Exception as e:
            logger.warning(f"HTTP节点 {node_id} 模板渲染失败: {e}")
            return content

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行HTTP请求"""
        config = node_config["data"].get("config", {})
        output_key = config.get("outputParams", "last_message")
        method = config.get("method", "GET").upper()
        url = config.get("url", "")
        timeout = int(config.get("timeout", 30))

        if not url:
            raise ValueError(f"HTTP节点 {node_id} 请求URL为空")

        # 获取一次模板上下文，后续所有渲染共用
        template_context = self.variable_manager.get_all_variables()

        try:
            request_kwargs = self._prepare_request_kwargs(config, node_id, timeout, template_context)
            response = self._send_http_request(method, url, request_kwargs, config, node_id, template_context)
            result = self._process_response(response)

            logger.info(f"HTTP节点 {node_id} 执行完成")
            return {output_key: result}

        except requests.exceptions.Timeout:
            raise ValueError(f"HTTP请求超时: {url}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"HTTP请求失败: {e}")

    def _prepare_request_kwargs(self, config: Dict[str, Any], node_id: str, timeout: int, template_context: Dict[str, Any]) -> Dict[str, Any]:
        """准备HTTP请求参数"""
        # 处理请求头
        headers_dict = self._process_key_value_pairs(config.get("headers", []), "header", node_id, template_context)

        # 处理GET参数
        params_dict = self._process_key_value_pairs(config.get("params", []), "参数", node_id, template_context)

        return {"timeout": timeout, "headers": headers_dict, "params": params_dict if params_dict else None}

    def _process_key_value_pairs(self, items: list | dict, item_type: str, node_id: str, template_context: Dict[str, Any]) -> Dict[str, str]:
        """处理键值对列表（如headers、params）"""
        if isinstance(items, dict):
            return items

        result_dict = {}
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "key" in item and "value" in item:
                    key = item["key"]
                    value = self._render_template(str(item["value"]), node_id, template_context)
                    result_dict[key] = value

        return result_dict

    def _prepare_request_body(self, config: Dict[str, Any], node_id: str, template_context: Dict[str, Any]):
        """准备请求体数据"""
        request_body = config.get("requestBody", "")
        if not request_body:
            return None

        rendered_body = self._render_template(str(request_body), node_id, template_context)

        # 尝试解析为JSON
        try:
            return json.loads(rendered_body)
        except json.JSONDecodeError:
            return rendered_body

    def _send_http_request(
        self, method: str, url: str, request_kwargs: Dict[str, Any], config: Dict[str, Any], node_id: str, template_context: Dict[str, Any]
    ):
        """发送HTTP请求"""
        logger.info(f"HTTP动作节点 {node_id}: {method} {url}")

        # 移除空的params以避免请求问题
        if request_kwargs.get("params") is None:
            request_kwargs.pop("params", None)

        # HTTP方法映射（使用安全请求）
        http_methods = {
            "GET": safe_get,
            "POST": safe_post,
            "PUT": safe_put,
            "PATCH": safe_patch,
            "DELETE": safe_delete,
        }

        http_func = http_methods.get(method)
        if not http_func:
            raise ValueError(f"不支持的HTTP方法: {method}")

        # GET请求不需要请求体
        if method == "GET":
            return http_func(url, **request_kwargs)

        # 其他方法需要处理请求体
        request_data = self._prepare_request_body(config, node_id, template_context)

        if request_data is not None:
            if isinstance(request_data, dict):
                return http_func(url, json=request_data, **request_kwargs)
            else:
                return http_func(url, data=request_data, **request_kwargs)
        else:
            return http_func(url, **request_kwargs)

    def _process_response(self, response) -> Any:
        """处理HTTP响应"""
        # 检查响应状态
        response.raise_for_status()

        # 尝试解析JSON响应，失败则返回文本
        try:
            return response.json()
        except ValueError:
            return response.text


class NotifyNode(BaseNodeExecutor):
    """通知节点"""

    SUPPORTED_ATTACHMENT_EXTENSIONS = {"md", "pdf", "docx"}

    @staticmethod
    def _build_email_attachment_filename(original_filename: str, index: int) -> str:
        extension = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        date_prefix = timezone.localtime().strftime("%Y%m%d")
        suffix = "" if index == 0 else f"_{index + 1}"
        return f"{date_prefix}{suffix}.{extension}" if extension else f"{date_prefix}{suffix}"

    def _render_content(self, content: str, node_id: str) -> str:
        """渲染通知内容

        Args:
            content: 内容模板
            node_id: 节点ID

        Returns:
            渲染后的内容
        """
        if not content:
            return content

        try:
            template_context = self.variable_manager.get_all_variables()
            return safe_render(str(content), template_context)
        except TemplateSecurityError as e:
            logger.error(f"通知节点 {node_id} 模板安全校验失败: {e}")
            raise ValueError(f"模板包含不安全内容: {e}")
        except Exception as e:
            logger.warning(f"通知节点 {node_id} 内容渲染失败: {e}")
            return content

    def _resolve_receivers(self, config: Dict[str, Any]) -> list[str]:
        receivers = config.get("notificationRecipients") or config.get("notificationReceivers", [])
        if receivers:
            return receivers

        if not self.variable_manager:
            return []

        flow_input = self.variable_manager.get_variable("flow_input", {}) or {}
        if not isinstance(flow_input, dict):
            return []

        fallback_receivers = flow_input.get("user_ids", [])
        return [str(receiver).strip() for receiver in fallback_receivers if str(receiver).strip()]

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行通知发送"""
        config = node_config["data"].get("config", {})
        output_key = config.get("outputParams", "last_message")
        logger.info("开始执行通知节点")
        try:
            # 获取通知配置参数 - 兼容多种字段名
            channel_id = config.get("notificationMethod")
            title = config.get("notificationTitle") or config.get("notificationSubject", "")
            content = config.get("notificationContent", "")
            receivers = self._resolve_receivers(config)
            notification_type = config.get("notificationType", "email")

            # 参数验证
            if not channel_id:
                error_msg = f"通知节点 {node_id} 缺少通知渠道ID (notificationMethod)"
                logger.error(error_msg)
                raise ValueError(error_msg)
            if not content:
                error_msg = f"通知节点 {node_id} 缺少通知内容 (notificationContent)"
                logger.error(error_msg)
                raise ValueError(error_msg)
            if not receivers:
                logger.warning(f"通知节点 {node_id} 缺少接收人列表,通知可能无法发送")

            # 渲染通知内容
            rendered_content = self._render_content(content, node_id)
            rendered_title = self._render_content(title, node_id) if title else ""
            attachments = []
            if notification_type == "email":
                attachments = self._build_attachments()

            # 调用发送通知接口
            result = self._send_notification(channel_id, rendered_title, rendered_content, receivers, node_id, attachments)

            logger.info(f"通知节点 {node_id} 执行完成: {result}")
            return {output_key: f"通知已发送: {rendered_title}"}

        except ValueError as e:
            # 配置错误应该向上传播,中断流程
            logger.error(f"通知节点 {node_id} 配置错误: {str(e)}")
            raise
        except Exception as e:
            # 其他错误记录后继续(避免阻塞流程)
            logger.error(f"通知节点 {node_id} 执行失败: {str(e)}")
            return {output_key: f"通知发送失败: {str(e)}"}

    def _build_attachments(self) -> list[dict]:
        execution_id = str(self.variable_manager.get_variable("execution_id", "") or "")
        if not execution_id:
            raise ValueError("当前工作流缺少 execution_id，无法解析附件")

        attachments = []
        assets = WorkflowAttachmentAsset.objects.filter(execution_id=execution_id).order_by("created_at", "id")
        for index, asset in enumerate(assets):
            extension = asset.filename.rsplit(".", 1)[-1].lower() if "." in asset.filename else ""
            if extension not in self.SUPPORTED_ATTACHMENT_EXTENSIONS:
                raise ValueError(f"附件 {asset.filename} 类型不支持发送")

            asset.file_knowledge.file.open("rb")
            try:
                file_bytes = asset.file_knowledge.file.read()
            finally:
                asset.file_knowledge.file.close()

            attachments.append(
                {
                    "filename": self._build_email_attachment_filename(asset.filename, index),
                    "content": base64.b64encode(file_bytes).decode("utf-8"),
                }
            )

        return attachments

    def _send_notification(
        self, channel_id: int, title: str, content: str, receivers: list, node_id: str, attachments: list[dict] | None = None
    ) -> Dict[str, Any]:
        """发送通知消息"""
        try:
            # 创建系统管理客户端
            system_client = SystemMgmt()

            # 调用发送通知接口
            result = system_client.send_msg_with_channel(
                channel_id=channel_id,
                title=title,
                content=content,
                receivers=receivers,
                attachments=attachments or None,
            )

            logger.info(f"通知节点 {node_id} 发送通知成功")
            return result

        except Exception as e:
            logger.error(f"通知节点 {node_id} 发送通知失败: {str(e)}")
            return {"result": False, "error": str(e)}


# 向后兼容的别名
HttpNode = HttpActionNode
