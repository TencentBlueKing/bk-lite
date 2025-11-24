"""
智能体节点
"""
from typing import Any, Dict

import jinja2
from django.conf import settings

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMSkill
from apps.opspilot.services.llm_service import llm_service
from apps.opspilot.utils.agui_chat import _generate_agui_stream
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_server_helper import ChatServerHelper
from apps.opspilot.utils.sse_chat import stream_chat


class AgentNode(BaseNodeExecutor):
    def __init__(self, variable_manager, workflow_instance=None):
        super().__init__(variable_manager)
        self.workflow_instance = workflow_instance

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
        llm_params, skill_name = self.set_llm_params(node_id, config, input_data)

        # 获取LLM模型并构建请求参数
        from apps.opspilot.models import LLMModel, SkillTypeChoices

        llm_model = LLMModel.objects.get(id=llm_params["llm_model"])
        show_think = llm_params.pop("show_think", True)
        llm_params.pop("group", None)

        chat_kwargs, doc_map, title_map = llm_service.format_chat_server_kwargs(llm_params, llm_model)

        # 根据技能类型选择不同的AGUI接口
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_chatbot_workflow_agui"
        if llm_params.get("skill_type") == SkillTypeChoices.BASIC_TOOL:
            url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_react_agent_agui"
        elif llm_params.get("skill_type") == SkillTypeChoices.PLAN_EXECUTE:
            url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_plan_and_execute_agent_agui"
        elif llm_params.get("skill_type") == SkillTypeChoices.LATS:
            url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_lats_agent_agui"

        headers = ChatServerHelper.get_chat_server_header()

        # 直接使用内部生成器函数，避免双重包装
        return _generate_agui_stream(url, headers, chat_kwargs, skill_name, show_think)

    def set_llm_params(self, node_id, config, input_data):
        input_key = config.get("inputParams", "last_message")
        skill_id = config.get("agent")

        if not skill_id:
            raise ValueError(f"智能体节点 {node_id} 缺少 skill_id 参数")

        skill_obj = LLMSkill.objects.filter(id=skill_id).first()
        if not skill_obj:
            raise ValueError(f"技能 {skill_id} 不存在")

        flow_input = self.variable_manager.get_variable("flow_input")
        # 获取消息内容，支持模板变量
        message = input_data.get(input_key)

        # 处理节点中的 prompt 参数和上传文件
        node_prompt = config.get("prompt", "")
        uploaded_files = config.get("uploadedFiles", [])
        final_message = message

        # 处理上传的文件内容
        files_content = ""
        if uploaded_files and isinstance(uploaded_files, list):
            file_contents = []
            for file_info in uploaded_files:
                if isinstance(file_info, dict) and "name" in file_info and "content" in file_info:
                    file_content = file_info["content"]
                    file_contents.append(file_content)

            if file_contents:
                contents = "\n".join(file_contents)
                files_content = f"""
        ### 补充背景知识:
        {contents}

        """

        if node_prompt or files_content:
            try:
                # 准备模板变量上下文 - 只使用全局变量
                template_context = self.variable_manager.get_all_variables()

                # 组合完整的节点prompt
                combined_prompt = ""
                # 添加文件内容
                if files_content:
                    combined_prompt += files_content
                if node_prompt:
                    # 使用 Jinja2 渲染 prompt
                    template = jinja2.Template(node_prompt)
                    rendered_prompt = template.render(**template_context)
                    combined_prompt += rendered_prompt

                # 将组合后的 prompt 追加到技能的 prompt 后面
                final_message = f"{combined_prompt}\n{message}"

            except Exception as e:
                logger.error(f"智能体节点 {node_id} prompt渲染失败: {str(e)}")
                # 如果渲染失败，使用原始内容
                combined_prompt = node_prompt + files_content
                final_message = f"{combined_prompt}\n{message}"

        # 构建LLM调用参数
        llm_params = {
            "llm_model": skill_obj.llm_model_id,
            "skill_prompt": skill_obj.skill_prompt,  # 使用处理后的prompt
            "temperature": skill_obj.temperature,
            "chat_history": [{"event": "user", "message": final_message}],
            "user_message": final_message,
            "conversation_window_size": skill_obj.conversation_window_size,
            "enable_rag": skill_obj.enable_rag,
            "rag_score_threshold": [{"knowledge_base": int(key), "score": float(value)} for key, value in skill_obj.rag_score_threshold_map.items()],
            "enable_rag_knowledge_source": skill_obj.enable_rag_knowledge_source,
            "show_think": skill_obj.show_think,
            "tools": skill_obj.tools,
            "skill_type": skill_obj.skill_type,
            "group": skill_obj.team[0],
            "user_id": flow_input.get("user_id", "anonymous"),
            "enable_km_route": skill_obj.enable_km_route,
            "km_llm_model": skill_obj.km_llm_model,
            "enable_suggest": skill_obj.enable_suggest,
            "enable_query_rewrite": skill_obj.enable_query_rewrite,
        }
        return llm_params, skill_obj.name

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        config = node_config["data"].get("config", {})
        output_key = config.get("outputParams", "last_message")
        llm_params, _ = self.set_llm_params(node_id, config, input_data)
        data, _, _ = llm_service.invoke_chat(llm_params)
        result = data["message"]

        return {output_key: result}


# 向后兼容的别名
AgentsNode = AgentNode
