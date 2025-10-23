"""
动作节点（HTTP请求、定时任务等）
"""
import json
from typing import Any, Dict

import jinja2
import requests

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.rpc.system_mgmt import SystemMgmt


class HttpActionNode(BaseNodeExecutor):
    """HTTP请求动作节点"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行HTTP请求"""
        config = node_config["data"].get("config", {})
        output_key = config.get("outputParams", "last_message")

        # 获取基本配置
        method = config.get("method", "GET").upper()
        url = config.get("url", "")
        timeout = int(config.get("timeout", 30))

        if not url:
            raise ValueError(f"HTTP动作节点 {node_id} 请求URL为空")

        try:
            # 准备请求参数
            request_kwargs = self._prepare_request_kwargs(config, node_id, timeout)

            # 发送HTTP请求
            response = self._send_http_request(method, url, request_kwargs, config, node_id)

            # 处理响应
            result = self._process_response(response)

            logger.info(f"HTTP动作节点 {node_id} 执行完成")
            return {output_key: result}

        except requests.exceptions.Timeout:
            raise ValueError(f"HTTP请求超时: {url}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"HTTP请求失败: {e}")

    def _prepare_request_kwargs(self, config: Dict[str, Any], node_id: str, timeout: int) -> Dict[str, Any]:
        """准备HTTP请求参数"""
        template_context = self.variable_manager.get_all_variables()

        # 处理请求头
        headers_dict = self._process_key_value_pairs(config.get("headers", []), "header", node_id, template_context)

        # 处理GET参数
        params_dict = self._process_key_value_pairs(config.get("params", []), "参数", node_id, template_context)

        return {"timeout": timeout, "headers": headers_dict, "params": params_dict if params_dict else None}

    def _process_key_value_pairs(self, items: list | dict, item_type: str, node_id: str, template_context: Dict[str, Any]) -> Dict[str, str]:
        """处理键值对列表（如headers、params）"""
        result_dict = {}

        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "key" in item and "value" in item:
                    key = item["key"]
                    value = item["value"]
                    # 使用Jinja2渲染值
                    try:
                        template = jinja2.Template(str(value))
                        rendered_value = template.render(**template_context)
                        result_dict[key] = rendered_value
                    except Exception as e:
                        logger.warning(f"HTTP节点 {node_id} {item_type}渲染失败: {e}")
                        result_dict[key] = value
        elif isinstance(items, dict):
            result_dict = items

        return result_dict

    def _prepare_request_body(self, config: Dict[str, Any], node_id: str, template_context: Dict[str, Any]):
        """准备请求体数据"""
        request_body = config.get("requestBody", "")
        if not request_body:
            return None

        try:
            # 使用Jinja2渲染请求体
            template = jinja2.Template(str(request_body))
            rendered_body = template.render(**template_context)

            # 尝试解析为JSON
            try:
                return json.loads(rendered_body)
            except json.JSONDecodeError:
                # 如果不是JSON，使用字符串
                return rendered_body

        except Exception as e:
            logger.warning(f"HTTP节点 {node_id} 请求体渲染失败: {e}")
            return request_body

    def _send_http_request(self, method: str, url: str, request_kwargs: Dict[str, Any], config: Dict[str, Any], node_id: str):
        """发送HTTP请求"""
        logger.info(f"HTTP动作节点 {node_id}: {method} {url}")

        # 移除空的params以避免请求问题
        if request_kwargs.get("params") is None:
            request_kwargs.pop("params", None)

        # HTTP方法映射
        http_methods = {
            "GET": requests.get,
            "POST": requests.post,
            "PUT": requests.put,
            "PATCH": requests.patch,
            "DELETE": requests.delete,
        }

        http_func = http_methods.get(method)
        if not http_func:
            raise ValueError(f"不支持的HTTP方法: {method}")

        # GET请求不需要请求体
        if method == "GET":
            return http_func(url, **request_kwargs)

        # 其他方法需要处理请求体
        template_context = self.variable_manager.get_all_variables()
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
    """通知节点 - 用于发送通知消息"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行通知发送"""
        config = node_config["data"].get("config", {})

        try:
            # 获取通知配置参数
            channel_id = config.get("notificationMethod")
            title = config.get("notificationSubject", "")
            content = config.get("notificationContent", "")
            receivers = config.get("notificationReceivers", [])

            # 参数验证
            if not channel_id:
                raise ValueError(f"通知节点 {node_id} 缺少通知渠道ID (notificationMethod)")

            if not content:
                raise ValueError(f"通知节点 {node_id} 缺少通知内容 (notificationContent)")

            # 使用Jinja2渲染通知内容
            template_context = self.variable_manager.get_all_variables()
            rendered_content = self._render_content(content, template_context, node_id)
            rendered_title = self._render_content(title, template_context, node_id) if title else ""

            # 调用发送通知接口
            result = self._send_notification(channel_id, rendered_title, rendered_content, receivers, node_id)

            logger.info(f"通知节点 {node_id} 执行完成，发送结果: {result}")
            return {}

        except Exception as e:
            logger.error(f"通知节点 {node_id} 执行失败: {str(e)}")
            # 返回失败结果而不是抛出异常，让工作流继续执行
            return {}

    def _render_content(self, content: str, template_context: Dict[str, Any], node_id: str) -> str:
        """使用Jinja2渲染内容"""
        try:
            template = jinja2.Template(str(content))
            return template.render(**template_context)
        except Exception as e:
            logger.warning(f"通知节点 {node_id} 内容渲染失败: {e}")
            return content

    def _send_notification(self, channel_id: int, title: str, content: str, receivers: list, node_id: str) -> Dict[str, Any]:
        """发送通知消息"""
        try:
            # 创建系统管理客户端
            system_client = SystemMgmt()

            # 调用发送通知接口
            result = system_client.send_msg_with_channel(channel_id=channel_id, title=title, content=content, receivers=receivers)

            logger.info(f"通知节点 {node_id} 发送通知成功")
            return result

        except Exception as e:
            logger.error(f"通知节点 {node_id} 发送通知失败: {str(e)}")
            return {"result": False, "error": str(e)}


# 向后兼容的别名
HttpNode = HttpActionNode
