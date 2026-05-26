"""
记忆读取节点 - 从记忆空间中检索相关记忆并注入上下文

使用方式：
1. 记忆内容会被设置到 variable_manager 的 "memory_context" 变量
2. 下游 agent 节点可以在 prompt 中使用 {{ memory_context }} 引用记忆内容
3. 记忆内容也会通过节点输出的 "memory_context" 字段传递
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class MemoryReadNode(BaseNodeExecutor):
    """记忆读取节点"""

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")
        # 支持两种字段名：memorySpace（前端表单）和 memory_space_id（旧格式）
        memory_space_id = config.get("memorySpace") or config.get("memory_space_id")
        top_k = config.get("top_k", 5)

        message = input_data.get(input_key, "")
        logger.info(f"[MemoryRead] 节点 {node_id} 开始执行")
        logger.info(f"[MemoryRead] 节点 {node_id} 配置: memory_space_id={memory_space_id}, top_k={top_k}, input_key={input_key}, output_key={output_key}")
        logger.info(f"[MemoryRead] 节点 {node_id} 输入数据 keys: {list(input_data.keys())}")
        logger.info(f"[MemoryRead] 节点 {node_id} 输入消息: {message[:100] if message else '(空)'}...")

        memory_context = ""
        memories_count = 0
        if memory_space_id:
            try:
                memories = list(Memory.objects.filter(memory_space_id=memory_space_id).order_by("-updated_at")[:top_k])
                memories_count = len(memories)
                if memories:
                    memory_context = "\n\n".join([f"## {m.title}\n{m.content}" for m in memories])
                    logger.info(f"[MemoryRead] 节点 {node_id} 读取到 {memories_count} 条记忆")
                    for m in memories:
                        logger.info(f"[MemoryRead] 节点 {node_id} 记忆条目: id={m.id}, title={m.title}, content_length={len(m.content)}")
                else:
                    logger.info(f"[MemoryRead] 节点 {node_id} 未找到记忆（记忆空间为空）")
            except MemorySpace.DoesNotExist:
                logger.error(f"[MemoryRead] 节点 {node_id} 记忆空间不存在: memory_space_id={memory_space_id}")
            except Exception as e:
                logger.error(f"[MemoryRead] 节点 {node_id} 读取失败: {e}", exc_info=True)
        else:
            logger.warning(f"[MemoryRead] 节点 {node_id} 未配置 memory_space_id，跳过读取")

        # 设置 memory_context 变量供下游节点使用
        # 下游 agent 节点可以在 prompt 中使用 {{ memory_context }} 引用
        if hasattr(self, "variable_manager") and self.variable_manager:
            self.variable_manager.set_variable("memory_context", memory_context)
            logger.info(f"[MemoryRead] 节点 {node_id} 已设置 variable_manager.memory_context (长度={len(memory_context)})")
        else:
            logger.warning(f"[MemoryRead] 节点 {node_id} variable_manager 不可用，无法设置全局变量")

        result = {output_key: message}
        if memory_context:
            result["memory_context"] = memory_context

        logger.info(f"[MemoryRead] 节点 {node_id} 执行完成: 读取记忆数={memories_count}, memory_context长度={len(memory_context)}")
        logger.info(f"[MemoryRead] 节点 {node_id} 输出 keys: {list(result.keys())}")
        return result
