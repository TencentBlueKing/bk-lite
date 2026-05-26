"""
记忆读取节点 - 从记忆空间中检索相关记忆并注入上下文

使用方式：
1. 记忆内容会被设置到 variable_manager 的 "memory_context" 变量
2. 下游 agent 节点可以在 prompt 中使用 {{ memory_context }} 引用记忆内容
3. 记忆内容也会通过节点输出的 "memory_context" 字段传递

权限规则：
- 个人记忆空间（scope=personal）：只读取当前用户的记忆
- 团队记忆空间（scope=team）：读取所有用户的记忆
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

        # 获取当前用户信息（从 flow_input 中获取）
        flow_input = {}
        if hasattr(self, "variable_manager") and self.variable_manager:
            flow_input = self.variable_manager.get_variable("flow_input") or {}
        user_id = flow_input.get("user_id", "") if isinstance(flow_input, dict) else ""
        # user_id 格式可能是 "username" 或 "username@domain"
        if "@" in user_id:
            owner_username, owner_domain = user_id.rsplit("@", 1)
        else:
            owner_username = user_id
            owner_domain = ""
        logger.info(f"[MemoryRead] 节点 {node_id} 当前用户: username={owner_username}, domain={owner_domain}")

        memory_context = ""
        memories_count = 0
        if memory_space_id:
            try:
                # 获取记忆空间，判断 scope
                memory_space = MemorySpace.objects.get(id=memory_space_id)
                logger.info(f"[MemoryRead] 节点 {node_id} 记忆空间: name={memory_space.name}, scope={memory_space.scope}")

                # 构建查询条件
                queryset = Memory.objects.filter(memory_space_id=memory_space_id)

                # 个人记忆空间：只读取当前用户的记忆（必须同时匹配 username 和 domain）
                if memory_space.scope == MemorySpace.SCOPE_PERSONAL:
                    if owner_username:
                        # username + domain 共同确定唯一用户
                        queryset = queryset.filter(owner_username=owner_username, owner_domain=owner_domain)
                        logger.info(f"[MemoryRead] 节点 {node_id} 个人记忆空间，过滤用户: {owner_username}@{owner_domain}")
                    else:
                        logger.warning(f"[MemoryRead] 节点 {node_id} 个人记忆空间但无法获取用户信息，返回空记忆")
                        queryset = queryset.none()
                else:
                    # 团队记忆空间：读取所有用户的记忆
                    logger.info(f"[MemoryRead] 节点 {node_id} 团队记忆空间，读取所有用户记忆")

                memories = list(queryset.order_by("-updated_at")[:top_k])
                memories_count = len(memories)
                if memories:
                    memory_context = "\n\n".join([f"## {m.title}\n{m.content}" for m in memories])
                    logger.info(f"[MemoryRead] 节点 {node_id} 读取到 {memories_count} 条记忆")
                    for m in memories:
                        logger.info(f"[MemoryRead] 节点 {node_id} 记忆条目: id={m.id}, title={m.title}, owner={m.owner_username}, content_length={len(m.content)}")
                else:
                    logger.info(f"[MemoryRead] 节点 {node_id} 未找到记忆（记忆空间为空或无匹配用户记忆）")
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
