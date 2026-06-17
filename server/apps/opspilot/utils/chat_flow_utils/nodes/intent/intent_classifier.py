"""意图分类节点 - 基于LLM识别用户输入的意图并路由到不同分支。"""

from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.safe_template import TemplateSecurityError, safe_render
from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class IntentClassifierNode(BaseNodeExecutor):
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

    def _render_prompt(self, prompt: str, node_id: str) -> str:
        """渲染补充分类规则中的模板变量。"""
        if not prompt:
            return ""

        try:
            template_context = self.variable_manager.get_all_variables()
            return safe_render(prompt, template_context)
        except TemplateSecurityError as e:
            logger.error("意图分类节点 %s 分类规则安全校验失败: %s", node_id, str(e))
            raise ValueError(f"模板包含不安全内容: {e}")
        except Exception as e:
            logger.error("意图分类节点 %s 分类规则渲染失败: %s", node_id, str(e))
            return prompt

    def _build_intent_prompt(self, node_id: str, intent_names: list[str], classification_rules: str) -> str:
        """构造最终用于分类的系统提示词。"""
        default_intent = intent_names[0] if intent_names else "未知"
        intent_list = "\n".join([f"- {name}" for name in intent_names]) if intent_names else "- 未知"
        intent_prompt = self.DEFAULT_SYSTEM_PROMPT.format(intent_list=intent_list, default_intent=default_intent)
        rendered_rules = self._render_prompt(classification_rules, node_id).strip()

        if not rendered_rules:
            return intent_prompt

        return f"{intent_prompt}\n\n### 补充分类规则\n{rendered_rules}"

    def _build_llm_params(
        self, node_id: str, config: Dict[str, Any], message: Any, flow_input: Dict[str, Any], intent_names: list[str]
    ) -> Dict[str, Any]:
        """构造意图分类节点的最小 LLM 调用参数。"""
        llm_model = config.get("llmModel")
        if not llm_model:
            raise ValueError(f"意图分类节点 {node_id} 缺少 llmModel 参数")

        return {
            "llm_model": llm_model,
            "skill_prompt": self._build_intent_prompt(node_id, intent_names, config.get("classificationRules", "")),
            "temperature": 0.1,
            "chat_history": [{"event": "user", "message": message}],
            "user_message": message,
            "conversation_window_size": 1,
            "show_think": False,
            "tools": [],
            "skill_type": SkillTypeChoices.BASIC_TOOL,
            "group": 0,
            "user_id": flow_input.get("user_id", "anonymous"),
            "enable_suggest": False,
            "enable_query_rewrite": False,
            "locale": flow_input.get("locale", "en"),
            "thread_id": flow_input.get("execution_id", ""),
            "execution_id": flow_input.get("execution_id", ""),
        }

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行意图分类节点

        节点配置示例：
        {
            "config": {
                "llmModel": 1,
                "classificationRules": "",
                "intents": [
                    {"name": "知识问答"},
                    {"name": "工单问题"}
                ],
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
            llm_params = self._build_llm_params(node_id, config, previous_node_output, flow_input, intent_names)
            result, _, _ = ChatService.invoke_chat(llm_params)

            # 检查 invoke_chat 是否执行失败
            if result.get("success") is False:
                logger.error("意图分类节点 %s invoke_chat 执行失败: %s", node_id, result.get("error"))
                return {
                    "success": False,
                    "error": result.get("error"),
                    "error_type": result.get("error_type"),
                    output_key: result.get("message", ""),
                    "intent_result": "error",
                    "previous_output": previous_node_output,
                }

            # 获取LLM返回的意图文本（如："知识问答"、"工单问题"）
            intent_text = result.get("message", "").strip()
            logger.info("意图分类节点 %s LLM返回意图: %r", node_id, intent_text)

            # 验证意图是否在配置的intents列表中
            if intent_text not in intent_names:
                logger.warning("意图分类节点 %s 返回的意图 %r 不在配置列表中: %r", node_id, intent_text, intent_names)
                # 不再静默回退到第一个意图，而是返回显式错误
                return {
                    "success": False,
                    "error": f"意图 '{intent_text}' 不在配置列表中: {intent_names}",
                    "error_type": "IntentNotFoundError",
                    output_key: intent_text,
                    "intent_result": "error",
                    "previous_output": previous_node_output,
                }

            # 返回结果，intent_result将用于匹配edge的sourceHandle
            return {
                output_key: intent_text,
                "intent_result": intent_text,  # 用于引擎匹配sourceHandle
                "previous_output": previous_node_output,  # 保存前置节点输出供后续使用
            }

        except Exception as e:
            logger.exception("意图分类节点 %s 执行失败: %r", node_id, e)
            # 不再静默回退到第一个意图，而是返回显式错误
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                output_key: str(e),
                "intent_result": "error",
                "previous_output": previous_node_output,
            }
