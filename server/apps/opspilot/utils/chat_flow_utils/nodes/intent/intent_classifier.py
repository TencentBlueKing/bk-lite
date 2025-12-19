"""
意图分类节点 - 基于LLM识别用户输入的意图并路由到不同分支
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode


class IntentClassifierNode(AgentNode):
    """意图分类节点

    功能：
    - 基于LLM自动识别用户输入的意图
    - 支持配置多个预定义意图类别
    - 输出意图标签和置信度
    - 支持路由到不同下游节点
    """

    # 默认系统提示词模板
    DEFAULT_SYSTEM_PROMPT = """你是一个专业的意图分类助手。你的任务是分析用户输入，准确识别其意图。

可用的意图类别：
1、工单问题
2、知识问答

识别用户问题，返回问题意图

要求：
1. 不需要直接回答用户问题
2. 返回结果只有两个，工单问题或者知识问答
3. 如果无法明确分类，返回“知识问答”
"""

    def __init__(self, variable_manager, workflow_instance=None):
        super().__init__(variable_manager, workflow_instance)

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行意图分类节点

        节点配置示例：
        {
            "config": {
                "llmModelId": "1",
                "agent": 1689,
                "intents": [
                    {"name": "知识问答"},
                    {"name": "工单问题"}
                ],
                "systemPrompt": "",
                "temperature": 0.1,
                "inputParams": "last_message",
                "outputParams": "last_message"
            }
        }

        路由通过edges的sourceHandle字段定义：
        {
            "source": "intent_classification-xxx",
            "sourceHandle": "知识问答",
            "target": "agents-xxx"
        }

        Args:
            node_id: 节点ID
            node_config: 节点配置
            input_data: 输入数据

        Returns:
            执行结果，包含识别的意图和路由信息
        """
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")
        intents = config.get("intents", [])

        # 保存前置节点的输出，用于后续target节点使用
        previous_node_output = input_data.get(input_key, "")
        self.variable_manager.set_variable("intent_previous_output", previous_node_output)

        try:
            # 调用父类Agent节点执行LLM意图分类
            result = super().execute(node_id, node_config, input_data)

            # 获取LLM返回的意图文本（如："知识问答"、"工单问题"）
            intent_text = result.get(output_key, "").strip()
            logger.info(f"意图分类节点 {node_id} LLM返回意图: {intent_text}")

            # 验证意图是否在配置的intents列表中
            intent_names = [intent.get("name", "").strip() for intent in intents]
            if intent_text not in intent_names:
                logger.warning(f"意图分类节点 {node_id} 返回的意图 '{intent_text}' 不在配置列表中: {intent_names}")
                # 使用第一个意图作为默认值
                if intent_names:
                    intent_text = intent_names[0]
                    logger.info(f"意图分类节点 {node_id} 使用默认意图: {intent_text}")

            # 返回结果，intent_result将用于匹配edge的sourceHandle
            return {
                output_key: intent_text,
                "intent_result": intent_text,  # 用于引擎匹配sourceHandle
                "previous_output": previous_node_output,  # 保存前置节点输出供后续使用
            }

        except Exception as e:
            logger.exception(f"意图分类节点 {node_id} 执行失败: {str(e)}")
            # 失败时使用第一个意图作为默认值
            default_intent = intents[0].get("name", "") if intents else "error"
            return {output_key: str(e), "intent_result": default_intent, "previous_output": previous_node_output}
