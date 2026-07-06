"""
智能体节点
"""

import json
import time
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.safe_template import TemplateSecurityError, safe_render
from apps.opspilot.models import LLMModel, LLMSkill, WorkflowAttachmentAsset
from apps.opspilot.services.builtin_tools import BUILTIN_ATTACHMENT_FILE_TOOL_NAME
from apps.opspilot.services.chat_service import ChatService, chat_service
from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt, build_skill_package_strategy, hydrate_skill_packages
from apps.opspilot.services.workflow_attachment_service import build_signed_attachment_download_url
from apps.opspilot.utils.agent_factory import create_agent_instance
from apps.opspilot.utils.chat_flow_utils.conversation_history import build_node_chat_history
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.prompt_utils import resolve_skill_params


class AgentNode(BaseNodeExecutor):
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
            # 记录可用的模板变量，特别是 memory_context
            memory_context = template_context.get("memory_context", "")
            logger.info(
                f"[Agent] 节点 {node_id} 模板变量: keys={list(template_context.keys())}, memory_context长度={len(memory_context) if memory_context else 0}"
            )
            rendered = safe_render(prompt, template_context)
            if memory_context and "memory_context" in prompt:
                logger.info(f"[Agent] 节点 {node_id} prompt 中使用了 memory_context")
            return rendered
        except TemplateSecurityError as e:
            logger.error(f"智能体节点 {node_id} prompt安全校验失败: {str(e)}")
            raise ValueError(f"模板包含不安全内容: {e}")
        except Exception as e:
            logger.error(f"智能体节点 {node_id} prompt渲染失败: {str(e)}")
            return prompt

    def _truncate_memory_context(self, memory_context: str, max_chars: int = 8000) -> str:
        """截断过长的记忆内容，避免超出 token 限制

        Args:
            memory_context: 记忆内容
            max_chars: 最大字符数（默认 8000，约 2000-4000 tokens）

        Returns:
            截断后的记忆内容
        """
        if not memory_context or len(memory_context) <= max_chars:
            return memory_context

        # 按记忆条目分割（每条记忆以 ## 开头）
        memories = memory_context.split("\n\n## ")
        if len(memories) <= 1:
            # 无法按条目分割，直接截断
            return memory_context[:max_chars] + "\n\n...(记忆内容过长，已截断)"

        # 保留第一条的 ## 前缀
        if memories[0].startswith("## "):
            memories[0] = memories[0][3:]

        # 逐条添加，直到达到限制
        result = []
        current_length = 0
        for i, mem in enumerate(memories):
            mem_with_prefix = f"## {mem}"

            if current_length + len(mem_with_prefix) + 4 > max_chars:  # +4 for "\n\n"
                if result:
                    result.append(f"\n\n...(还有 {len(memories) - i} 条记忆未显示)")
                break

            if result:
                result.append("\n\n")
            result.append(mem_with_prefix)
            current_length += len(mem_with_prefix) + 4

        return "".join(result)

    def _build_final_message(self, message, node_prompt: str, uploaded_files: list, node_id: str) -> str:
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

        # 自动注入记忆内容（如果存在）
        memory_content = ""
        if hasattr(self, "variable_manager") and self.variable_manager:
            memory_context = self.variable_manager.get_variable("memory_context", "")
            if memory_context:
                # 截断过长的记忆内容，避免超出 token 限制
                truncated_memory = self._truncate_memory_context(memory_context)
                memory_content = f"""### 相关记忆（来自记忆空间）:
{truncated_memory}

"""
                logger.info(f"[Agent] 节点 {node_id} 自动注入记忆内容: 原始长度={len(memory_context)}, 截断后长度={len(truncated_memory)}")

        if not files_content and not rendered_prompt and not memory_content:
            return message

        combined_prompt = memory_content + files_content + rendered_prompt
        if isinstance(message, str):
            return f"{combined_prompt}\n{message}"
        for i in message:
            if i["type"] == "message":
                i["message"] = f"{combined_prompt}\n{i['message']}"
                break
        return message

    def _build_llm_params(
        self,
        skill: LLMSkill,
        final_message: str,
        flow_input: Dict[str, Any],
        node_id: str = "",
        raw_message: Any = None,
    ) -> Dict[str, Any]:
        """构建LLM调用参数

        Args:
            skill: 技能对象
            final_message: 最终消息
            flow_input: 流程输入
            node_id: 当前执行的节点ID（优先级高于 flow_input["node_id"]）
            raw_message: 节点消费的原始输入，用于判断是否注入跨轮会话历史

        Returns:
            LLM参数字典
        """
        # 优先使用调用方传入的当前节点 ID；flow_input["node_id"] 存储的是入口节点 ID，
        # 不是当前智能体节点的 ID，直接使用会导致附件 source_node_id 错误。
        effective_node_id = node_id or self.variable_manager.get_variable("current_node_id", "")
        resolved_prompt = resolve_skill_params(skill.skill_prompt, skill.skill_params)
        skill_packages = hydrate_skill_packages(getattr(skill, "skill_packages", []) or [])
        resolved_prompt, matched_skill_packages = build_skill_package_prompt(
            base_prompt=resolved_prompt,
            skill_packages=skill_packages,
            user_message=final_message,
            available_tool_names={tool.get("name") for tool in (skill.tools or []) if isinstance(tool, dict) and tool.get("name")},
        )
        skill_package_strategy = build_skill_package_strategy(matched_skill_packages)
        chat_history = build_node_chat_history(
            self.variable_manager,
            raw_input_message=final_message if raw_message is None else raw_message,
            final_message=final_message,
        )
        return {
            "llm_model": skill.llm_model_id,
            "skill_prompt": resolved_prompt,
            "matched_skill_packages": matched_skill_packages,
            **skill_package_strategy,
            "temperature": skill.temperature,
            "chat_history": chat_history,
            "user_message": final_message,
            "conversation_window_size": skill.conversation_window_size,
            "show_think": skill.show_think,
            "tools": skill.tools,
            "skill_type": skill.skill_type,
            "group": skill.team[0],
            "user_id": flow_input.get("user_id", "anonymous"),
            "enable_suggest": skill.enable_suggest,
            "enable_query_rewrite": skill.enable_query_rewrite,
            "locale": flow_input.get("locale", "en"),  # 用户语言设置，用于 browser-use 输出国际化
            "thread_id": flow_input.get("execution_id", ""),
            "execution_id": flow_input.get("execution_id", ""),
            "node_id": effective_node_id,
            "flow_id": self.variable_manager.get_variable("flow_id", ""),
            "trigger_type": self._resolve_trigger_type(flow_input),
        }

    @staticmethod
    def _skill_supports_attachment_generation(skill: LLMSkill) -> bool:
        return any(isinstance(tool, dict) and tool.get("name") == BUILTIN_ATTACHMENT_FILE_TOOL_NAME for tool in (skill.tools or []))

    def _sync_generated_attachment_link(self, node_id: str, execution_id: str) -> Dict[str, Any]:
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id or not execution_id:
            return {}

        asset = (
            WorkflowAttachmentAsset.objects.filter(execution_id=execution_id, source_node_id=normalized_node_id)
            .order_by("-created_at", "-id")
            .first()
        )
        if not asset:
            return {}

        download_url = build_signed_attachment_download_url(asset)
        self.variable_manager.set_variable(normalized_node_id, download_url)
        return {
            normalized_node_id: download_url,
            "generated_attachment": {
                "attachment_id": asset.attachment_id,
                "filename": asset.filename,
                "file_url": download_url,
                "mime_type": asset.mime_type,
            },
        }

    def sse_execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]):
        """流式执行agent节点，返回异步生成器"""
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        skill_id = config.get("agent")

        llm_params, skill_name, _ = self.set_llm_params(node_id, config, input_data)

        # 导入 create_stream_generator 而不是 stream_chat
        from apps.opspilot.utils.sse_chat import create_stream_generator

        # 返回异步生成器而不是 StreamingHttpResponse
        return create_stream_generator(llm_params, skill_name, {}, None, input_data.get(input_key), skill_id)

    def agui_execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]):
        """AGUI协议流式执行agent节点，返回异步生成器"""
        config = node_config["data"].get("config", {})

        # 获取 LLM 参数
        llm_params, skill_name, _ = self.set_llm_params(node_id, config, input_data)

        # 获取 LLM 模型并构建请求参数
        llm_model = LLMModel.objects.get(id=llm_params["llm_model"])
        show_think = llm_params.pop("show_think", True)
        skill_type = llm_params.get("skill_type")
        llm_params.pop("group", 0)

        chat_kwargs, _, _ = chat_service.format_chat_server_kwargs(llm_params, llm_model)
        # 创建 agent 实例
        graph, request = create_agent_instance(skill_type, chat_kwargs)

        # 直接返回异步生成器
        async def generate_agui_stream():
            """异步生成器：直接生成 AGUI 数据流"""
            try:
                logger.info(f"[AgentNode-AGUI] 开始流式处理 - skill_name: {skill_name}, node_id: {node_id}, show_think: {show_think}")

                chunk_index = 0
                async for sse_line in graph.agui_stream(request):
                    yield sse_line

                logger.info(f"[AgentNode-AGUI] 流式处理完成 - 生成 {chunk_index} 个chunk")
            except Exception as e:
                logger.error(f"[AgentNode-AGUI] stream error: {e}", exc_info=True)
                error_data = {
                    "type": "ERROR",
                    "error": f"节点执行错误: {str(e)}",
                    "timestamp": int(time.time() * 1000),
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

        return generate_agui_stream()

    @staticmethod
    def _resolve_trigger_type(flow_input: Dict[str, Any]) -> str:
        """根据 entry_type 映射到 trigger_type（用于审批策略判断）"""
        entry_type = flow_input.get("entry_type", "")
        if entry_type in ("celery", "test"):
            return "unattended"
        elif entry_type in ("enterprise_wechat", "enterprise_wechat_aibot", "dingtalk", "wechat_official"):
            return "third_party"
        else:
            return "interactive"

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
        llm_params = self._build_llm_params(skill, final_message, flow_input, node_id=node_id, raw_message=message)

        return llm_params, skill.name, self._skill_supports_attachment_generation(skill)

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """非流式执行agent节点"""
        config = node_config["data"].get("config", {})
        output_key = config.get("outputParams", "last_message")

        llm_params, _, supports_attachment_generation = self.set_llm_params(node_id, config, input_data)

        # 使用同步版本的 invoke_chat,避免异步上下文冲突
        data, _, _ = ChatService.invoke_chat(llm_params)

        # 检查执行是否失败
        if data.get("success") is False:
            return {
                "success": False,
                "error": data.get("error"),
                "error_type": data.get("error_type"),
                output_key: data["message"],
            }

        result = {output_key: data["message"]}
        if supports_attachment_generation:
            result.update(self._sync_generated_attachment_link(node_id, llm_params.get("execution_id", "")))
        if data.get("browser_steps"):
            result["browser_steps"] = data["browser_steps"]
        return result


# 向后兼容的别名
AgentsNode = AgentNode
