"""
记忆读取节点 - 从记忆空间中检索相关记忆并注入上下文

使用方式：
1. 记忆内容会被设置到 variable_manager 的 "memory_context" 变量
2. 下游 agent 节点可以在 prompt 中使用 {{ memory_context }} 引用记忆内容
3. 记忆内容也会通过节点输出的 "memory_context" 字段传递

权限规则：
- 个人记忆空间（scope=personal）：只读取当前用户的记忆
- 团队记忆空间（scope=team）：读取组织的记忆

支持的存储引擎：
- local: 本地 PostgreSQL 存储
- mem0: Mem0 云服务
- zep: Zep 云服务
- custom: 自定义 API
"""
from typing import Any, Dict

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.memory.engines.base import MemoryEntity
from apps.opspilot.memory.engines.registry import MemoryEngineRegistry
from apps.opspilot.models.memory_mgmt import MemorySpace
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


def build_memory_entity(memory_space: MemorySpace, user_id: str, flow_input: dict = None) -> MemoryEntity:
    """根据记忆空间 scope 构建 MemoryEntity

    Args:
        memory_space: 记忆空间对象
        user_id: 用户 ID（格式：username 或 username@domain）
        flow_input: 可选的 flow_input 上下文，用于覆盖团队记忆的 organization_id

    Returns:
        MemoryEntity: 记忆实体
    """
    if memory_space.scope == MemorySpace.SCOPE_PERSONAL:
        # 个人记忆：使用 user_id
        return MemoryEntity(user_id=user_id)
    else:
        # 团队记忆：优先使用 flow_input.team（单个组织 ID），回退到 memory_space.team[0]
        fi_team = (flow_input or {}).get("team") if isinstance(flow_input, dict) else None
        # 兼容历史的单元素列表写法
        if isinstance(fi_team, (list, tuple)):
            fi_team = fi_team[0] if fi_team else None
        if fi_team is not None and str(fi_team).strip() != "":
            organization_id = int(fi_team)
        else:
            space_teams = memory_space.team or []
            organization_id = space_teams[0] if space_teams else None
        return MemoryEntity(organization_id=organization_id)


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
        logger.info(
            f"[MemoryRead] 节点 {node_id} 配置: memory_space_id={memory_space_id}, " f"top_k={top_k}, input_key={input_key}, output_key={output_key}"
        )
        logger.info(f"[MemoryRead] 节点 {node_id} 输入数据 keys: {list(input_data.keys())}")
        logger.info(f"[MemoryRead] 节点 {node_id} 输入消息: {message[:100] if message else '(空)'}...")

        # 获取当前用户信息（从 flow_input 中获取）
        flow_input = {}
        if hasattr(self, "variable_manager") and self.variable_manager:
            flow_input = self.variable_manager.get_variable("flow_input") or {}
        user_id = flow_input.get("user_id", "") if isinstance(flow_input, dict) else ""
        logger.info(f"[MemoryRead] 节点 {node_id} 当前用户: user_id={user_id}")

        memory_context = ""
        memories_count = 0
        if memory_space_id:
            try:
                # 获取记忆空间
                memory_space = MemorySpace.objects.get(id=memory_space_id)
                logger.info(
                    f"[MemoryRead] 节点 {node_id} 记忆空间: name={memory_space.name}, "
                    f"scope={memory_space.scope}, storage_type={memory_space.storage_type}"
                )

                engine = MemoryEngineRegistry.get_engine(memory_space_id)
                logger.info(f"[MemoryRead] 节点 {node_id} 使用引擎: {type(engine).__name__}")

                # 当 flow_input.user_ids 非空且为个人记忆时，按干系人逐个读取并聚合
                user_ids = flow_input.get("user_ids") if isinstance(flow_input, dict) else None
                if memory_space.scope == MemorySpace.SCOPE_PERSONAL and user_ids:
                    target_users = list(user_ids)
                else:
                    target_users = [user_id]

                context_parts = []
                raw_all = []
                for target_user in target_users:
                    entity = build_memory_entity(memory_space, target_user, flow_input)
                    logger.info(
                        f"[MemoryRead] 节点 {node_id} 构建实体 (user={target_user}): " f"user_id={entity.user_id}, organization_id={entity.organization_id}"
                    )
                    per_result = engine.read(entity=entity, query=message, top_k=top_k)
                    if per_result.context:
                        context_parts.append(per_result.context)
                    raw_all.extend(per_result.raw_memories)

                memory_context = "\n\n---\n\n".join(context_parts)
                memories_count = len(raw_all)

                if memories_count > 0:
                    logger.info(f"[MemoryRead] 节点 {node_id} 读取到 {memories_count} 条记忆")
                else:
                    logger.info(f"[MemoryRead] 节点 {node_id} 未找到记忆（记忆空间为空或无匹配记忆）")
            except MemorySpace.DoesNotExist:
                logger.error(f"[MemoryRead] 节点 {node_id} 记忆空间不存在: memory_space_id={memory_space_id}")
            except ValueError as e:
                logger.error(f"[MemoryRead] 节点 {node_id} 引擎错误: {e}")
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
