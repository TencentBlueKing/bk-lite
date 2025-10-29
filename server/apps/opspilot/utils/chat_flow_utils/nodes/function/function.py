"""
函数节点（自定义逻辑处理）
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class FunctionNode(BaseNodeExecutor):
    """函数节点 - 用于执行自定义函数逻辑"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")

        # 从input_data根据input_key获取输入内容
        input_message = input_data.get(input_key, "")

        # 获取函数参数，优先从config中获取，兼容旧版params
        params = config.get("params", input_data.get("params", {}))

        # 获取函数名称和参数
        function_name = params.get("function_name", "")
        function_args = params.get("function_args", {})

        if not function_name:
            # 如果没有指定函数，返回输入数据
            logger.info(f"函数节点 {node_id} 无指定函数，返回输入: {input_message}")
            return {output_key: input_message}

        # 这里可以扩展为动态函数调用
        logger.info(f"函数节点 {node_id} 执行函数: {function_name}")

        # 示例函数执行逻辑（可以扩展）
        result = None
        if function_name == "echo":
            result = function_args.get("message", input_message)
        elif function_name == "upper":
            text = function_args.get("text", input_message)
            result = str(text).upper()
        elif function_name == "lower":
            text = function_args.get("text", input_message)
            result = str(text).lower()
        else:
            raise ValueError(f"未知的函数: {function_name}")

        return {output_key: result}
