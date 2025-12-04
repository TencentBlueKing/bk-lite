"""
分支节点（条件节点）
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.safe_eval import evaluate_condition


class BranchNode(BaseNodeExecutor):
    """分支节点 - 支持多种条件判断操作符"""

    # 支持的条件操作符
    OPERATORS = {
        "equals": lambda a, b: str(a) == str(b),
        "==": lambda a, b: str(a) == str(b),
        "not_equals": lambda a, b: str(a) != str(b),
        "!=": lambda a, b: str(a) != str(b),
        "contains": lambda a, b: str(b) in str(a),
        "not_contains": lambda a, b: str(b) not in str(a),
        "starts_with": lambda a, b: str(a).startswith(str(b)),
        "ends_with": lambda a, b: str(a).endswith(str(b)),
    }

    def __init__(self, variable_manager, start_node_id=None):
        super().__init__(variable_manager)
        self.start_node_id = start_node_id

    def _get_compare_data(self, condition_field: str, input_message: str) -> str:
        """获取比较数据

        Args:
            condition_field: 条件字段
            input_message: 输入消息

        Returns:
            比较数据
        """
        variables = self.variable_manager.get_all_variables()

        if condition_field == "triggerType":
            return self.start_node_id or variables.get("start_node", "")
        elif condition_field in variables:
            return variables[condition_field]
        else:
            return input_message

    def _evaluate_condition(self, compare_data: str, operator: str, value: str, node_id: str) -> bool:
        """评估条件

        Args:
            compare_data: 比较数据
            operator: 操作符
            value: 比较值
            node_id: 节点ID

        Returns:
            判断结果
        """
        # 使用内置操作符
        if operator in self.OPERATORS:
            return self.OPERATORS[operator](compare_data, value)

        # 使用安全求值作为后备
        try:
            condition_expr = f"data {operator} '{value}'"
            return evaluate_condition(condition_expr, data=str(compare_data))
        except Exception as e:
            logger.error(f"条件表达式求值失败: {condition_expr}, 错误: {str(e)}")
            return False

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行分支节点"""
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")
        input_message = input_data.get(input_key, "")

        # 获取条件参数
        condition_field = config.get("conditionField", "triggerType")
        condition_operator = config.get("conditionOperator", "equals")
        condition_value = config.get("conditionValue", "")

        # 获取比较数据
        compare_data = self._get_compare_data(condition_field, input_message)

        # 执行条件判断
        result = self._evaluate_condition(compare_data, condition_operator, condition_value, node_id)

        logger.info(f"分支节点 {node_id}: {condition_field}={compare_data} {condition_operator} {condition_value} = {result}")

        return {output_key: result, "condition_result": result}


# 向后兼容的别名
ConditionNode = BranchNode
