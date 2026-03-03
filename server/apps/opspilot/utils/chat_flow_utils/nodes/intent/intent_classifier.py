"""
意图分类节点 - 基于LLM识别用户输入的意图并路由到不同分支
"""

from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMSkill
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
    DEFAULT_SYSTEM_PROMPT = """## 意图识别任务

你现在是一个**意图分类器**，不是对话助手。你的唯一任务是分析用户输入并识别其意图类别。

### 可选意图类别
{intent_list}

### 输出规则（必须严格遵守）
1. **只返回意图名称本身**，不要包含任何其他内容
2. **禁止**回答用户问题、提供解释、添加标点或格式
3. **禁止**输出"用户意图是"、"我认为"等前缀
4. 返回内容必须与上述意图类别**完全一致**（包括大小写和标点）
5. 如果无法确定，返回：{default_intent}

### 正确示例
用户输入："服务器宕机了怎么办"
正确输出：工单问题

用户输入："什么是K8s"
正确输出：知识问答

### 错误示例（禁止）
❌ "用户的意图是：知识问答"
❌ "这是一个知识问答类型的问题"
❌ "知识问答。"
"""

    def __init__(self, variable_manager, workflow_instance=None):
        super().__init__(variable_manager, workflow_instance)

    def _build_llm_params(self, skill: LLMSkill, final_message: str, flow_input: Dict[str, Any]) -> Dict[str, Any]:
        """构建LLM调用参数，追加意图分类专用prompt

        重写父类方法，将 DEFAULT_SYSTEM_PROMPT 追加到原有 skill_prompt 后面

        Args:
            skill: 技能对象
            final_message: 最终消息
            flow_input: 流程输入

        Returns:
            LLM参数字典
        """
        # 调用父类方法获取基础参数
        llm_params = super()._build_llm_params(skill, final_message, flow_input)

        # 获取意图列表并格式化
        intent_names = flow_input.get("_intent_names", [])
        default_intent = intent_names[0] if intent_names else "未知"

        # 格式化意图列表（带序号，更清晰）
        intent_list = "\n".join([f"- {name}" for name in intent_names]) if intent_names else "- 未知"

        # 渲染意图分类专用prompt
        intent_prompt = self.DEFAULT_SYSTEM_PROMPT.format(intent_list=intent_list, default_intent=default_intent)

        # 将意图分类prompt追加到原有skill_prompt后面
        original_prompt = llm_params.get("skill_prompt", "")
        if original_prompt:
            llm_params["skill_prompt"] = f"{original_prompt}\n\n{intent_prompt}"
        else:
            llm_params["skill_prompt"] = intent_prompt

        return llm_params

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
        intent_names = [intent.get("name", "").strip() for intent in intents]

        # 保存前置节点的输出，用于后续target节点使用
        previous_node_output = input_data.get(input_key, "")
        self.variable_manager.set_variable("intent_previous_output", previous_node_output)

        # 将意图名称列表传递给 _build_llm_params 使用
        flow_input = self.variable_manager.get_variable("flow_input") or {}
        flow_input["_intent_names"] = intent_names
        self.variable_manager.set_variable("flow_input", flow_input)

        try:
            # 调用父类Agent节点执行LLM意图分类
            result = super().execute(node_id, node_config, input_data)

            # 获取LLM返回的意图文本（如："知识问答"、"工单问题"）
            intent_text = result.get(output_key, "").strip()
            logger.info("意图分类节点 %s LLM返回意图: %r", node_id, intent_text)

            # 验证意图是否在配置的intents列表中
            if intent_text not in intent_names:
                logger.warning("意图分类节点 %s 返回的意图 %r 不在配置列表中: %r", node_id, intent_text, intent_names)
                # 使用第一个意图作为默认值
                if intent_names:
                    intent_text = intent_names[0]
                    logger.info("意图分类节点 %s 使用默认意图: %r", node_id, intent_text)

            # 返回结果，intent_result将用于匹配edge的sourceHandle
            return {
                output_key: intent_text,
                "intent_result": intent_text,  # 用于引擎匹配sourceHandle
                "previous_output": previous_node_output,  # 保存前置节点输出供后续使用
            }

        except Exception as e:
            logger.exception("意图分类节点 %s 执行失败: %r", node_id, e)
            # 失败时使用第一个意图作为默认值
            default_intent = intents[0].get("name", "") if intents else "error"
            return {output_key: str(e), "intent_result": default_intent, "previous_output": previous_node_output}
