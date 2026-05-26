"""
记忆写入节点 - 异步将内容写入记忆空间（透传输入）

作为支线节点存在，不影响主流程的输入输出。
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class MemoryWriteNode(BaseNodeExecutor):
    """记忆写入节点 - 触发异步写入任务，透传输入"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")
        # 支持两种字段名：memorySpace（前端表单）和 memory_space_id（旧格式）
        memory_space_id = config.get("memorySpace") or config.get("memory_space_id")
        title = config.get("title", "")

        message = input_data.get(input_key, "")
        logger.info(f"[MemoryWrite] 节点 {node_id} 开始执行: memory_space_id={memory_space_id}, title={title}, input_key={input_key}")
        logger.info(f"[MemoryWrite] 节点 {node_id} 输入数据 keys: {list(input_data.keys())}")
        logger.info(f"[MemoryWrite] 节点 {node_id} 消息内容: {message[:100] if message else '(空)'}")

        if memory_space_id and message:
            try:
                from apps.opspilot.tasks import process_memory_write

                # 从 variable_manager 获取原始 flow_input，提取 user_id
                # flow_input 在引擎初始化时被存储，包含完整的用户信息
                flow_input = {}
                if hasattr(self, "variable_manager") and self.variable_manager:
                    flow_input = self.variable_manager.get_variable("flow_input", {}) or {}

                user_id = flow_input.get("user_id", "") or input_data.get("user_id", "")
                if "@" in user_id:
                    username, domain = user_id.rsplit("@", 1)
                else:
                    username = user_id or "system"
                    domain = ""

                logger.info(f"[MemoryWrite] 节点 {node_id} 触发异步写入任务: username={username}, domain={domain}")
                process_memory_write.delay(
                    memory_space_id=memory_space_id,
                    title=title or f"自动记忆-{node_id}",
                    content=message,
                    owner_username=username,
                    owner_domain=domain,
                )
                logger.info(f"[MemoryWrite] 节点 {node_id} 异步任务已提交")
            except Exception as e:
                logger.error(f"[MemoryWrite] 节点 {node_id} 触发写入任务失败: {e}", exc_info=True)
        else:
            logger.warning(f"[MemoryWrite] 节点 {node_id} 跳过写入: memory_space_id={memory_space_id}, message_empty={not message}")

        # 透传输入，不影响主流程
        logger.info(f"[MemoryWrite] 节点 {node_id} 透传输出: {output_key}={message[:50] if message else '(空)'}...")
        return {output_key: message}
