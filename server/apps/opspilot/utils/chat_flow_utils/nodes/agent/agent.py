"""
智能体节点
"""
from typing import Any, Dict

import jinja2

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMModel, LLMSkill
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.services.llm_service import llm_service
from apps.opspilot.utils.agent_factory import create_agent_instance
from apps.opspilot.utils.agui_chat import _generate_agui_stream
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.sse_chat import stream_chat


class AgentNode(BaseNodeExecutor):
    def __init__(self, variable_manager, workflow_instance=None):
        super().__init__(variable_manager)
        self.workflow_instance = workflow_instance

    def _get_skill(self, skill_id: str) -> LLMSkill:
        """获取技能对象

        Args:
            skill_id: 技能ID

        Returns:
            技能对象

        Raises:
            ValueError: 技能不存在
        """
        skill = LLMSkill.objects.filter(id=skill_id).first()
        if not skill:
            raise ValueError(f"技能 {skill_id} 不存在")
        return skill

    def _process_uploaded_files(self, uploaded_files: list) -> str:
        """处理上传文件内容

        Args:
            uploaded_files: 上传文件列表

        Returns:
            格式化后的文件内容
        """
        if not uploaded_files or not isinstance(uploaded_files, list):
            return ""

        file_contents = []
        for file_info in uploaded_files:
            if isinstance(file_info, dict) and "name" in file_info and "content" in file_info:
                file_contents.append(file_info["content"])

        if not file_contents:
            return ""

        contents = "\n".join(file_contents)
        return f"""### 补充背景知识:
{contents}

"""

    def _render_prompt(self, prompt: str, node_id: str) -> str:
        """渲染prompt模板

        Args:
            prompt: prompt模板
            node_id: 节点ID

        Returns:
            渲染后的prompt
        """
        if not prompt:
            return ""

        try:
            template_context = self.variable_manager.get_all_variables()
            template = jinja2.Template(prompt)
            return template.render(**template_context)
        except Exception as e:
            logger.error(f"智能体节点 {node_id} prompt渲染失败: {str(e)}")
            return prompt

    def _build_final_message(self, message: str, node_prompt: str, uploaded_files: list, node_id: str) -> str:
        """构建最终消息

        Args:
            message: 原始消息
            node_prompt: 节点prompt
            uploaded_files: 上传文件列表
            node_id: 节点ID

        Returns:
            最终消息
        """
        files_content = self._process_uploaded_files(uploaded_files)
        rendered_prompt = self._render_prompt(node_prompt, node_id)

        if not files_content and not rendered_prompt:
            return message

        combined_prompt = files_content + rendered_prompt
        return f"{combined_prompt}\n{message}"

    def _build_llm_params(self, skill: LLMSkill, final_message: str, flow_input: Dict[str, Any]) -> Dict[str, Any]:
        """构建LLM调用参数

        Args:
            skill: 技能对象
            final_message: 最终消息
            flow_input: 流程输入

        Returns:
            LLM参数字典
        """
        return {
            "llm_model": skill.llm_model_id,
            "skill_prompt": skill.skill_prompt,
            "temperature": skill.temperature,
            "chat_history": [{"event": "user", "message": final_message}],
            "user_message": final_message,
            "conversation_window_size": skill.conversation_window_size,
            "enable_rag": skill.enable_rag,
            "rag_score_threshold": [{"knowledge_base": int(key), "score": float(value)} for key, value in skill.rag_score_threshold_map.items()],
            "enable_rag_knowledge_source": skill.enable_rag_knowledge_source,
            "show_think": skill.show_think,
            "tools": skill.tools,
            "skill_type": skill.skill_type,
            "group": skill.team[0],
            "user_id": flow_input.get("user_id", "anonymous"),
            "enable_km_route": skill.enable_km_route,
            "km_llm_model": skill.km_llm_model,
            "enable_suggest": skill.enable_suggest,
            "enable_query_rewrite": skill.enable_query_rewrite,
        }

    def sse_execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]):
        """流式执行agent节点，yield SSE格式数据"""
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        skill_id = config.get("agent")

        llm_params, skill_name = self.set_llm_params(node_id, config, input_data)
        return stream_chat(llm_params, skill_name, {}, None, input_data.get(input_key), skill_id)

    def agui_execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]):
        """AGUI协议流式执行agent节点，yield AGUI格式数据"""
        config = node_config["data"].get("config", {})

        # 获取 LLM 参数
        llm_params, skill_name = self.set_llm_params(node_id, config, input_data)

        # 获取 LLM 模型并构建请求参数
        llm_model = LLMModel.objects.get(id=llm_params["llm_model"])
        show_think = llm_params.pop("show_think", True)
        skill_type = llm_params.get("skill_type")
        llm_params.pop("group", 0)

        chat_kwargs, _, _ = llm_service.format_chat_server_kwargs(llm_params, llm_model)

        # 创建 agent 实例
        graph, request = create_agent_instance(skill_type, chat_kwargs)

        # 调用内部生成器函数
        return _generate_agui_stream(graph, request, skill_name, show_think)

    def set_llm_params(self, node_id: str, config: Dict[str, Any], input_data: Dict[str, Any]):
        """设置LLM参数

        Args:
            node_id: 节点ID
            config: 节点配置
            input_data: 输入数据

        Returns:
            (llm_params, skill_name) 元组
        """
        input_key = config.get("inputParams", "last_message")
        skill_id = config.get("agent")

        if not skill_id:
            raise ValueError(f"智能体节点 {node_id} 缺少 skill_id 参数")

        # 获取技能对象
        skill = self._get_skill(skill_id)

        # 获取消息内容
        message = input_data.get(input_key)
        flow_input = self.variable_manager.get_variable("flow_input")

        # 构建最终消息（包含节点prompt和文件内容）
        node_prompt = config.get("prompt", "")
        uploaded_files = config.get("uploadedFiles", [])
        final_message = self._build_final_message(message, node_prompt, uploaded_files, node_id)

        # 构建LLM参数
        llm_params = self._build_llm_params(skill, final_message, flow_input)

        return llm_params, skill.name

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """非流式执行agent节点"""
        config = node_config["data"].get("config", {})
        output_key = config.get("outputParams", "last_message")

        llm_params, _ = self.set_llm_params(node_id, config, input_data)

        # 使用同步版本的 invoke_chat,避免异步上下文冲突
        data, _, _ = ChatService.invoke_chat(llm_params)

        return {output_key: data["message"]}


# 向后兼容的别名
AgentsNode = AgentNode
