"""
分支节点（条件节点）
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.safe_eval import evaluate_condition


class BranchNode(BaseNodeExecutor):
    """分支节点（条件判断）"""

    def __init__(self, variable_manager, start_node_id=None):
        super().__init__(variable_manager)
        self.start_node_id = start_node_id

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")

        # 从input_data根据input_key获取输入内容
        input_message = input_data.get(input_key, "")

        # 获取条件参数
        condition_field = config.get("conditionField", "triggerType")
        condition_operator = config.get("conditionOperator", "equals")
        condition_value = config.get("conditionValue", "")

        # 获取变量管理器中的变量
        variables = {}
        if hasattr(self, "variable_manager"):
            variables = self.variable_manager.get_all_variables()

        # 获取比较的数据
        if condition_field == "triggerType":
            # 对于触发类型，获取起始节点ID
            compare_data = self.start_node_id or variables.get("start_node", "")
        elif condition_field in variables:
            compare_data = variables[condition_field]
        else:
            compare_data = input_message

        # 执行条件判断
        result = False
        if condition_operator in ["equals", "=="]:
            result = str(compare_data) == str(condition_value)
        elif condition_operator in ["not_equals", "!="]:
            result = str(compare_data) != str(condition_value)
        elif condition_operator in ["contains"]:
            result = str(condition_value) in str(compare_data)
        elif condition_operator in ["not_contains"]:
            result = str(condition_value) not in str(compare_data)
        elif condition_operator in ["starts_with"]:
            result = str(compare_data).startswith(str(condition_value))
        elif condition_operator in ["ends_with"]:
            result = str(compare_data).endswith(str(condition_value))
        else:
            # 使用安全求值作为后备方案
            try:
                condition_expr = f"data {condition_operator} '{condition_value}'"
                result = evaluate_condition(condition_expr, data=str(compare_data))
            except Exception as e:
                logger.error(f"条件表达式求值失败: {condition_expr}, 错误: {str(e)}")
                result = False

        logger.info(f"分支节点 {node_id}: {condition_field}={compare_data} {condition_operator} {condition_value} = {result}")

        # 返回结果包含条件判断结果，用于分支选择
        return {output_key: result, "condition_result": result}  # 用于引擎判断分支路径


# 向后兼容的别名
ConditionNode = BranchNode
