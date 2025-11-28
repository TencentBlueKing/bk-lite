"""
函数节点（自定义逻辑处理）
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class FunctionNode(BaseNodeExecutor):
    """函数节点 - 支持基本字符串处理函数"""

    # 支持的内置函数
    BUILTIN_FUNCTIONS = {
        "echo": lambda args, default: args.get("message", default),
        "upper": lambda args, default: str(args.get("text", default)).upper(),
        "lower": lambda args, default: str(args.get("text", default)).lower(),
    }

    def _execute_function(self, function_name: str, function_args: Dict[str, Any], default_input: str) -> str:
        """执行函数

        Args:
            function_name: 函数名
            function_args: 函数参数
            default_input: 默认输入值

        Returns:
            执行结果

        Raises:
            ValueError: 不支持的函数
        """
        func = self.BUILTIN_FUNCTIONS.get(function_name)
        if not func:
            raise ValueError(f"未知的函数: {function_name}")

        return func(function_args, default_input)

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行函数节点"""
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")
        input_message = input_data.get(input_key, "")

        # 获取函数参数
        params = config.get("params", input_data.get("params", {}))
        function_name = params.get("function_name", "")
        function_args = params.get("function_args", {})

        if not function_name:
            logger.info(f"函数节点 {node_id} 无指定函数，返回输入")
            return {output_key: input_message}

        logger.info(f"函数节点 {node_id} 执行函数: {function_name}")
        result = self._execute_function(function_name, function_args, input_message)

        return {output_key: result}
